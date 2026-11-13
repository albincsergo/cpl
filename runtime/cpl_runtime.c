// CPL runtime library.
//
// Compiled programs call into this file for everything that is too annoying to write in raw LLVM
// IR: strings, vectors, maps, buffered input/output, the program's stack and runtime errors.
//
// It makes the trade-offs a short-lived competitive programming solution can afford and real
// software can't:
// - All memory comes from one bump allocator (an "arena") carved out of a huge address space
//   reservation. Allocating is a pointer bump, memory arrives already zeroed, and nothing is ever
//   freed. A vector or string whose buffer is the newest allocation grows in place.
// - The program runs on a stack of up to 16 GB, so deep recursion just works.
// - Strings are immutable, but appending to the newest string of a buffer writes in place, so
//   building a string piece by piece is linear instead of quadratic.

#define _GNU_SOURCE
#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>

// key kinds shared by maps and sorting
enum { KIND_SIGNED = 0, KIND_UNSIGNED = 1, KIND_DOUBLE = 2, KIND_STRING = 3 };

// region output
static char outBuffer[1 << 20];
static size_t outLength = 0;

static void writeAll(int fd, const char *data, size_t length) {
    size_t offset = 0;
    while (offset < length) {
        ssize_t written = write(fd, data + offset, length - offset);
        if (written <= 0) {
            if (written < 0 && errno == EINTR) continue;
            return;
        }
        offset += (size_t)written;
    }
}

void cpl_flush(void) {
    writeAll(1, outBuffer, outLength);
    outLength = 0;
}

static void outWrite(const char *data, size_t length) {
    if (outLength + length > sizeof(outBuffer)) {
        cpl_flush();
        if (length > sizeof(outBuffer)) {
            writeAll(1, data, length);
            return;
        }
    }
    memcpy(outBuffer + outLength, data, length);
    outLength += length;
}

static void outChar(char c) {
    if (outLength == sizeof(outBuffer)) cpl_flush();
    outBuffer[outLength++] = c;
}

static int formatUnsigned(uint64_t value, char *buffer) {
    char digits[24];
    int count = 0;
    do {
        digits[count++] = (char)('0' + value % 10);
        value /= 10;
    } while (value > 0);

    for (int i = 0; i < count; i++) buffer[i] = digits[count - 1 - i];
    return count;
}

void cpl_print_i64(int64_t value) {
    char buffer[24];
    int length = 0;
    uint64_t magnitude = (uint64_t)value;
    if (value < 0) {
        buffer[length++] = '-';
        magnitude = 0 - magnitude;
    }
    length += formatUnsigned(magnitude, buffer + length);
    outWrite(buffer, (size_t)length);
}

void cpl_print_u64(uint64_t value) {
    char buffer[24];
    outWrite(buffer, (size_t)formatUnsigned(value, buffer));
}

void cpl_print_f64(double value) {
    char buffer[64];
    int length = snprintf(buffer, sizeof(buffer), "%g", value);
    outWrite(buffer, (size_t)length);
}

void cpl_print_char(int8_t c) { outChar((char)c); }

void cpl_print_bool(int8_t value) {
    if (value) outWrite("true", 4);
    else outWrite("false", 5);
}
// endregion

// region errors
__attribute__((noreturn)) static void panic(const char *format, ...) {
    cpl_flush();
    char message[512];
    va_list args;
    va_start(args, format);
    int length = vsnprintf(message, sizeof(message), format, args);
    va_end(args);
    if (length < 0) length = 0;
    if (length > (int)sizeof(message) - 1) length = (int)sizeof(message) - 1;

    writeAll(2, "~~~ RUNTIME ERROR: ", 19);
    writeAll(2, message, (size_t)length);
    writeAll(2, "\n", 1);
    // _exit, not exit: there is nothing to clean up, and the program may be on its own thread
    _exit(1);
}

void cpl_panic_index(int64_t index, int64_t length) {
    panic("index %lld is out of bounds for length %lld", (long long)index, (long long)length);
}

void cpl_panic_div(void) { panic("division by zero"); }

void cpl_panic_nil(void) { panic("accessed a field of nil"); }

void cpl_panic_empty(void) { panic("vector is empty"); }
// endregion

// region memory
// One bump allocator for everything. Chunks come from huge MAP_NORESERVE reservations, so the
// kernel only hands out (zeroed) pages as they're touched. Nothing is ever freed, so memory is
// always zero the first time it's used.
static char *arenaTop = NULL;
static char *arenaEnd = NULL;
static size_t nextChunkSize = 0;

#define ALIGNMENT 8
#define MIN_CHUNK ((size_t)16 << 20)
#define HUGE_CHUNK ((size_t)64 << 30)
#define FIRST_LIMITED_CHUNK ((size_t)64 << 20)

static size_t alignUp(size_t size) { return (size + ALIGNMENT - 1) & ~(size_t)(ALIGNMENT - 1); }

// the address space limit (ulimit -v) or 0 if there is none; judges often set one
static size_t addressSpaceLimit(void) {
    struct rlimit limit;
    if (getrlimit(RLIMIT_AS, &limit) == 0 && limit.rlim_cur != RLIM_INFINITY) return (size_t)limit.rlim_cur;
    return 0;
}

static void newChunk(size_t needed) {
    // without an address space limit, one huge reservation is free; with one, start small and
    // double, so that unused reservations never waste more than half of what's allowed
    if (nextChunkSize == 0) nextChunkSize = addressSpaceLimit() ? FIRST_LIMITED_CHUNK : HUGE_CHUNK;
    size_t first = nextChunkSize > needed ? nextChunkSize : alignUp(needed);
    for (size_t size = first; size >= MIN_CHUNK && size >= needed; size /= 2) {
        void *memory = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
        if (memory == MAP_FAILED) continue;
#ifdef MADV_HUGEPAGE
        // big arrays get 2 MB pages: fewer TLB misses on random access
        madvise(memory, size, MADV_HUGEPAGE);
#endif
        arenaTop = memory;
        arenaEnd = (char *)memory + size;
        nextChunkSize = size < HUGE_CHUNK ? size * 2 : size;
        return;
    }

    size_t size = needed > MIN_CHUNK ? needed : MIN_CHUNK;
    void *memory = calloc(1, size);
    if (memory == NULL) panic("out of memory");
    arenaTop = memory;
    arenaEnd = (char *)memory + size;
}

static void *arenaAlloc(size_t size) {
    size = alignUp(size > 0 ? size : 1);
    if ((size_t)(arenaEnd - arenaTop) < size) newChunk(size);
    void *memory = arenaTop;
    arenaTop += size;
    return memory;
}

// grows the newest allocation in place, if `end` is where it currently ends
static int arenaExtend(char *end, size_t extra) {
    extra = alignUp(extra);
    if (end != arenaTop || (size_t)(arenaEnd - arenaTop) < extra) return 0;
    arenaTop += extra;
    return 1;
}

void *cpl_alloc(int64_t size) { return arenaAlloc((size_t)size); }
// endregion

// region strings
// A string is a header { len, data }. Bit 63 of len marks strings whose data is the start of a
// growable buffer, which is preceded by a StrBuffer. Whichever string ends exactly at the buffer's
// used end may append in place; everyone else copies. Old strings never see the appended bytes
// because their length doesn't change, so strings stay immutable.
typedef struct {
    int64_t len;
    char *data;
} CplStr;

typedef struct {
    char *used;
    char *capacityEnd;
} StrBuffer;

#define GROWABLE ((int64_t)1 << 62)

static int64_t strLength(const CplStr *s) { return s ? (s->len & (GROWABLE - 1)) : 0; }

static CplStr *strHeader(char *data, int64_t length, int growable) {
    CplStr *s = arenaAlloc(sizeof(CplStr));
    s->len = length | (growable ? GROWABLE : 0);
    s->data = data;
    return s;
}

// a new string of `length` bytes (to be filled in by the caller) with room to grow to `capacity`
static CplStr *strNew(int64_t length, int64_t capacity) {
    if (capacity < length) capacity = length;
    // the header goes first, so the buffer is the newest allocation and can grow in place
    CplStr *s = arenaAlloc(sizeof(CplStr));
    StrBuffer *buffer = arenaAlloc(sizeof(StrBuffer) + (size_t)capacity);
    char *data = (char *)(buffer + 1);
    buffer->used = data + length;
    buffer->capacityEnd = data + alignUp((size_t)capacity);
    s->len = length | GROWABLE;
    s->data = data;
    return s;
}

static CplStr *strFromBytes(const char *bytes, int64_t length) {
    CplStr *s = strNew(length, length);
    if (length) memcpy(s->data, bytes, (size_t)length);
    return s;
}

int64_t cpl_str_len(CplStr *s) { return strLength(s); }

void cpl_print_str(CplStr *s) {
    if (s != NULL) outWrite(s->data, (size_t)strLength(s));
}

// appends bytes to a, in place when a is the newest string of its buffer
static CplStr *appendBytes(CplStr *a, const char *bytes, int64_t lengthB) {
    int64_t lengthA = strLength(a);

    if (lengthA > 0 && (a->len & GROWABLE)) {
        StrBuffer *buffer = (StrBuffer *)a->data - 1;
        if (a->data + lengthA == buffer->used) {
            int64_t room = buffer->capacityEnd - buffer->used;
            // out of room but the buffer is the newest allocation: double it in place
            if (room < lengthB && arenaExtend(buffer->capacityEnd, (size_t)(lengthA + lengthB))) {
                buffer->capacityEnd += alignUp((size_t)(lengthA + lengthB));
                room = buffer->capacityEnd - buffer->used;
            }
            if (room >= lengthB) {
                memcpy(buffer->used, bytes, (size_t)lengthB);
                buffer->used += lengthB;
                return strHeader(a->data, lengthA + lengthB, 1);
            }
        }
    }

    // copy into a new buffer with room to spare, so the next append is cheap
    CplStr *s = strNew(lengthA + lengthB, 2 * (lengthA + lengthB) + 16);
    if (lengthA) memcpy(s->data, a->data, (size_t)lengthA);
    memcpy(s->data + lengthA, bytes, (size_t)lengthB);
    return s;
}

CplStr *cpl_str_concat(CplStr *a, CplStr *b) {
    int64_t lengthB = strLength(b);
    if (lengthB == 0) return a;
    if (strLength(a) == 0) return b;
    return appendBytes(a, b->data, lengthB);
}

// s + c without building a one character string first
CplStr *cpl_str_append_char(CplStr *a, int8_t c) {
    char byte = (char)c;
    return appendBytes(a, &byte, 1);
}

int32_t cpl_str_cmp(CplStr *a, CplStr *b) {
    int64_t lengthA = strLength(a), lengthB = strLength(b);
    int64_t shorter = lengthA < lengthB ? lengthA : lengthB;
    int result = shorter ? memcmp(a->data, b->data, (size_t)shorter) : 0;
    if (result != 0) return result < 0 ? -1 : 1;
    return lengthA < lengthB ? -1 : (lengthA > lengthB ? 1 : 0);
}

int8_t cpl_str_at(CplStr *s, int64_t index) {
    int64_t length = strLength(s);
    if (index < 0 || index >= length) cpl_panic_index(index, length);
    return (int8_t)s->data[index];
}

// substrings are views into the original bytes: O(1), no copying
CplStr *cpl_str_sub(CplStr *s, int64_t start, int64_t count) {
    int64_t length = strLength(s);
    if (start < 0 || start > length) cpl_panic_index(start, length);
    if (count < 0) panic("substring length can't be negative");
    if (count > length - start) count = length - start;
    if (count == 0) return NULL;
    return strHeader(s->data + start, count, 0);
}

CplStr *cpl_str_from_char(int8_t c) {
    char byte = (char)c;
    return strFromBytes(&byte, 1);
}

CplStr *cpl_str_from_i64(int64_t value) {
    char buffer[32];
    return strFromBytes(buffer, snprintf(buffer, sizeof(buffer), "%lld", (long long)value));
}

CplStr *cpl_str_from_u64(uint64_t value) {
    char buffer[32];
    return strFromBytes(buffer, snprintf(buffer, sizeof(buffer), "%llu", (unsigned long long)value));
}

CplStr *cpl_str_from_f64(double value) {
    char buffer[64];
    return strFromBytes(buffer, snprintf(buffer, sizeof(buffer), "%g", value));
}

CplStr *cpl_str_from_bool(int8_t value) { return value ? strFromBytes("true", 4) : strFromBytes("false", 5); }

// fixed number of digits after the decimal point, like cout << fixed << setprecision(d)
CplStr *cpl_str_prec(double value, int64_t digits) {
    if (digits < 0) digits = 0;
    if (digits > 100) digits = 100;
    char buffer[512];
    int length = snprintf(buffer, sizeof(buffer), "%.*f", (int)digits, value);
    if (length >= (int)sizeof(buffer)) {
        CplStr *s = strNew(length + 1, length + 1);
        snprintf(s->data, (size_t)length + 1, "%.*f", (int)digits, value);
        s->len = length | GROWABLE;
        ((StrBuffer *)s->data - 1)->used = s->data + length;
        return s;
    }
    return strFromBytes(buffer, length);
}

// strings aren't NUL terminated, so the C parsers get a terminated copy
static char *terminatedCopy(CplStr *s) {
    int64_t length = strLength(s);
    char *copy = arenaAlloc((size_t)length + 1);
    if (length) memcpy(copy, s->data, (size_t)length);
    copy[length] = '\0';
    return copy;
}

int64_t cpl_str_to_i64(CplStr *s) {
    if (strLength(s) == 0) panic("can't convert an empty string to an integer");
    char *text = terminatedCopy(s);
    char *end;
    errno = 0;
    long long value = strtoll(text, &end, 10);
    if (*end != '\0' || errno != 0) panic("can't convert \"%s\" to an integer", text);
    return (int64_t)value;
}

double cpl_str_to_f64(CplStr *s) {
    if (strLength(s) == 0) panic("can't convert an empty string to a number");
    char *text = terminatedCopy(s);
    char *end;
    double value = strtod(text, &end);
    if (*end != '\0') panic("can't convert \"%s\" to a number", text);
    return value;
}
// endregion

// region input
static char inBuffer[1 << 16];
static size_t inLength = 0;
static size_t inPosition = 0;
static int inEnded = 0;

static int peekChar(void) {
    if (inPosition == inLength) {
        if (inEnded) return -1;
        // like cin being tied to cout: show pending output before blocking on input
        cpl_flush();
        ssize_t count;
        do {
            count = read(0, inBuffer, sizeof(inBuffer));
        } while (count < 0 && errno == EINTR);
        if (count <= 0) {
            inEnded = 1;
            return -1;
        }
        inLength = (size_t)count;
        inPosition = 0;
    }
    return (unsigned char)inBuffer[inPosition];
}

static int nextChar(void) {
    int c = peekChar();
    if (c >= 0) inPosition++;
    return c;
}

static int isSpace(int c) {
    return c == ' ' || c == '\n' || c == '\t' || c == '\r' || c == '\v' || c == '\f';
}

static void skipSpaces(void) {
    while (isSpace(peekChar())) inPosition++;
}

// reads the next whitespace separated word into a reusable buffer
static char *readWord(size_t *lengthOut) {
    static char *word = NULL;
    static size_t capacity = 0;
    size_t length = 0;

    skipSpaces();
    int c;
    while ((c = peekChar()) >= 0 && !isSpace(c)) {
        if (length + 1 >= capacity) {
            capacity = capacity ? capacity * 2 : 64;
            char *bigger = realloc(word, capacity);
            if (bigger == NULL) panic("out of memory");
            word = bigger;
        }
        word[length++] = (char)c;
        inPosition++;
    }
    if (word == NULL) {
        capacity = 64;
        word = malloc(capacity);
        if (word == NULL) panic("out of memory");
    }
    word[length] = '\0';
    *lengthOut = length;
    return word;
}

int8_t cpl_eof(void) {
    skipSpaces();
    return peekChar() < 0;
}

int64_t cpl_read_i64(void) {
    skipSpaces();
    if (peekChar() < 0) return 0;

    int negative = 0;
    if (peekChar() == '-' || peekChar() == '+') negative = nextChar() == '-';
    if (peekChar() < '0' || peekChar() > '9') panic("expected an integer in the input");

    uint64_t value = 0;
    while (peekChar() >= '0' && peekChar() <= '9') value = value * 10 + (uint64_t)(nextChar() - '0');
    return negative ? (int64_t)(0 - value) : (int64_t)value;
}

uint64_t cpl_read_u64(void) {
    skipSpaces();
    if (peekChar() < 0) return 0;
    if (peekChar() == '+') nextChar();
    if (peekChar() < '0' || peekChar() > '9') panic("expected an unsigned integer in the input");

    uint64_t value = 0;
    while (peekChar() >= '0' && peekChar() <= '9') value = value * 10 + (uint64_t)(nextChar() - '0');
    return value;
}

double cpl_read_f64(void) {
    size_t length;
    char *word = readWord(&length);
    if (length == 0) return 0.0;

    char *end;
    double value = strtod(word, &end);
    if (*end != '\0') panic("expected a number in the input, got \"%s\"", word);
    return value;
}

int8_t cpl_read_char(void) {
    skipSpaces();
    int c = nextChar();
    return c < 0 ? 0 : (int8_t)c;
}

int8_t cpl_read_bool(void) {
    size_t length;
    char *word = readWord(&length);
    if (strcmp(word, "true") == 0 || strcmp(word, "1") == 0) return 1;
    if (length == 0 || strcmp(word, "false") == 0 || strcmp(word, "0") == 0) return 0;
    panic("expected a boolean in the input, got \"%s\"", word);
}

CplStr *cpl_read_str(void) {
    size_t length;
    char *word = readWord(&length);
    return length ? strFromBytes(word, (int64_t)length) : NULL;
}

// reads the rest of the current line, without the line break
CplStr *cpl_read_line(void) {
    CplStr *line = strNew(0, 64);
    StrBuffer *buffer = (StrBuffer *)line->data - 1;
    int c;
    while ((c = nextChar()) >= 0 && c != '\n') {
        if (buffer->used == buffer->capacityEnd) {
            line = cpl_str_append_char(line, (int8_t)c);
            buffer = (StrBuffer *)line->data - 1;
            continue;
        }
        *buffer->used++ = (char)c;
        line->len++;
    }
    int64_t length = strLength(line);
    if (length > 0 && line->data[length - 1] == '\r') {
        line->len--;
        buffer->used--;
    }
    return strLength(line) ? line : NULL;
}
// endregion

// region math
int64_t cpl_ipow(int64_t base, int64_t exponent) {
    if (exponent < 0) {
        if (base == 1) return 1;
        if (base == -1) return (exponent & 1) ? -1 : 1;
        if (base == 0) cpl_panic_div();
        return 0;
    }

    // wraps around on overflow, like the rest of the integer arithmetic
    uint64_t result = 1, factor = (uint64_t)base;
    while (exponent > 0) {
        if (exponent & 1) result *= factor;
        factor *= factor;
        exponent >>= 1;
    }
    return (int64_t)result;
}
// endregion

// region sorting
static int sortKind;
static int64_t sortSize;

static int64_t loadSigned(const void *p) {
    switch (sortSize) {
        case 1: return *(const int8_t *)p;
        case 2: return *(const int16_t *)p;
        case 4: return *(const int32_t *)p;
        default: return *(const int64_t *)p;
    }
}

static uint64_t loadUnsigned(const void *p) {
    switch (sortSize) {
        case 1: return *(const uint8_t *)p;
        case 2: return *(const uint16_t *)p;
        case 4: return *(const uint32_t *)p;
        default: return *(const uint64_t *)p;
    }
}

static int compareElements(const void *a, const void *b) {
    switch (sortKind) {
        case KIND_SIGNED: {
            int64_t x = loadSigned(a), y = loadSigned(b);
            return (x > y) - (x < y);
        }
        case KIND_UNSIGNED: {
            uint64_t x = loadUnsigned(a), y = loadUnsigned(b);
            return (x > y) - (x < y);
        }
        case KIND_DOUBLE: {
            double x = *(const double *)a, y = *(const double *)b;
            return (x > y) - (x < y);
        }
        default:
            return cpl_str_cmp(*(CplStr *const *)a, *(CplStr *const *)b);
    }
}

// specialized sorts for the common element types, so they don't pay for qsort's indirect comparisons
#define DEFINE_SORT(name, type)                                                       \
    static void name(type *data, int64_t count) {                                     \
        while (count > 16) {                                                          \
            type a = data[0], b = data[count / 2], c = data[count - 1];               \
            type pivot = a < b ? (b < c ? b : (a < c ? c : a)) : (a < c ? a : (b < c ? c : b)); \
            int64_t i = 0, j = count - 1;                                             \
            while (i <= j) {                                                          \
                while (data[i] < pivot) i++;                                          \
                while (data[j] > pivot) j--;                                          \
                if (i <= j) {                                                         \
                    type swap = data[i];                                              \
                    data[i] = data[j];                                                \
                    data[j] = swap;                                                   \
                    i++;                                                              \
                    j--;                                                              \
                }                                                                     \
            }                                                                         \
            /* recurse into the smaller half, loop on the bigger one */               \
            if (j + 1 < count - i) {                                                  \
                name(data, j + 1);                                                    \
                data += i;                                                            \
                count -= i;                                                           \
            } else {                                                                  \
                name(data + i, count - i);                                            \
                count = j + 1;                                                        \
            }                                                                         \
        }                                                                             \
        for (int64_t k = 1; k < count; k++) {                                         \
            type value = data[k];                                                     \
            int64_t m = k - 1;                                                        \
            while (m >= 0 && data[m] > value) {                                       \
                data[m + 1] = data[m];                                                \
                m--;                                                                  \
            }                                                                         \
            data[m + 1] = value;                                                      \
        }                                                                             \
    }

DEFINE_SORT(sortI32, int32_t)
DEFINE_SORT(sortI64, int64_t)
DEFINE_SORT(sortU32, uint32_t)
DEFINE_SORT(sortU64, uint64_t)
DEFINE_SORT(sortF64, double)

static void sortRaw(char *data, int64_t count, int64_t elemSize, int32_t kind) {
    if (count < 2) return;
    if (kind == KIND_SIGNED && elemSize == 4) {
        sortI32((int32_t *)data, count);
        return;
    }
    if (kind == KIND_SIGNED && elemSize == 8) {
        sortI64((int64_t *)data, count);
        return;
    }
    if (kind == KIND_UNSIGNED && elemSize == 4) {
        sortU32((uint32_t *)data, count);
        return;
    }
    if (kind == KIND_UNSIGNED && elemSize == 8) {
        sortU64((uint64_t *)data, count);
        return;
    }
    // NaNs would break the quicksort's assumptions, so doubles with NaNs go through qsort
    if (kind == KIND_DOUBLE) {
        int hasNaN = 0;
        for (int64_t i = 0; i < count && !hasNaN; i++) hasNaN = isnan(((double *)data)[i]);
        if (!hasNaN) {
            sortF64((double *)data, count);
            return;
        }
    }
    sortKind = kind;
    sortSize = elemSize;
    qsort(data, (size_t)count, (size_t)elemSize, compareElements);
}
// endregion

// region vectors
typedef struct {
    int64_t len;
    int64_t cap;
    int64_t elemSize;
    char *data;
} CplVec;

CplVec *cpl_vec_new(int64_t elemSize, int64_t length) {
    if (length < 0) panic("vector size can't be negative (got %lld)", (long long)length);
    CplVec *v = arenaAlloc(sizeof(CplVec));
    v->elemSize = elemSize;
    v->len = length;
    v->cap = length;
    // arena memory is always zero the first time, so the elements already have their default value
    v->data = length > 0 ? arenaAlloc((size_t)(length * elemSize)) : NULL;
    return v;
}

// makes room for at least one more element; the compiler inlines the case where there is room
void cpl_vec_grow(CplVec *v) {
    int64_t capacity = v->cap ? v->cap * 2 : 4;
    size_t oldBytes = alignUp((size_t)(v->cap * v->elemSize));
    size_t newBytes = (size_t)(capacity * v->elemSize);

    // the newest allocation grows in place, no copying
    if (v->data != NULL && arenaExtend(v->data + oldBytes, newBytes - oldBytes)) {
        v->cap = capacity;
        return;
    }

    char *data = arenaAlloc(newBytes);
    if (v->len) memcpy(data, v->data, (size_t)(v->len * v->elemSize));
    v->data = data;
    v->cap = capacity;
}

// appends an element and returns a pointer to it (the element may hold old data after a pop)
char *cpl_vec_push(CplVec *v) {
    if (v->len == v->cap) cpl_vec_grow(v);
    return v->data + v->len++ * v->elemSize;
}

void cpl_vec_pop(CplVec *v) {
    if (v->len == 0) cpl_panic_empty();
    v->len--;
}

void cpl_vec_clear(CplVec *v) { v->len = 0; }

void cpl_vec_sort(CplVec *v, int32_t kind) { sortRaw(v->data, v->len, v->elemSize, kind); }

void cpl_vec_reverse(CplVec *v) {
    char temporary[16];
    int64_t size = v->elemSize;
    for (int64_t i = 0, j = v->len - 1; i < j; i++, j--) {
        memcpy(temporary, v->data + i * size, (size_t)size);
        memcpy(v->data + i * size, v->data + j * size, (size_t)size);
        memcpy(v->data + j * size, temporary, (size_t)size);
    }
}
// endregion

// region maps
// open addressing hash map; every key and value fits in 8 bytes
typedef struct {
    uint64_t key;
    uint64_t value;
    uint8_t state;  // 0 empty, 1 used, 2 deleted
} Entry;

typedef struct {
    Entry *entries;
    int64_t capacity;
    int64_t size;
    int64_t deleted;
    int32_t kind;
} CplMap;

static uint64_t hashKey(const CplMap *m, uint64_t key) {
    if (m->kind == KIND_STRING) {
        CplStr *s = (CplStr *)(uintptr_t)key;
        uint64_t hash = 1469598103934665603ULL;
        int64_t length = strLength(s);
        for (int64_t i = 0; i < length; i++) hash = (hash ^ (uint8_t)s->data[i]) * 1099511628211ULL;
        key = hash;
    }
    // splitmix64 finalizer, so sequential keys don't cluster
    key += 0x9e3779b97f4a7c15ULL;
    key = (key ^ (key >> 30)) * 0xbf58476d1ce4e5b9ULL;
    key = (key ^ (key >> 27)) * 0x94d049bb133111ebULL;
    return key ^ (key >> 31);
}

static uint64_t normalizeKey(const CplMap *m, uint64_t key) {
    // -0.0 and 0.0 are the same key
    if (m->kind == KIND_DOUBLE && key == 0x8000000000000000ULL) return 0;
    return key;
}

static int keysEqual(const CplMap *m, uint64_t a, uint64_t b) {
    if (m->kind == KIND_STRING) return a == b || cpl_str_cmp((CplStr *)(uintptr_t)a, (CplStr *)(uintptr_t)b) == 0;
    return a == b;
}

CplMap *cpl_map_new(int32_t kind) {
    CplMap *m = arenaAlloc(sizeof(CplMap));
    m->kind = kind;
    m->capacity = 16;
    m->entries = arenaAlloc(sizeof(Entry) * (size_t)m->capacity);
    return m;
}

static Entry *findEntry(const CplMap *m, uint64_t key) {
    uint64_t mask = (uint64_t)m->capacity - 1;
    for (uint64_t i = hashKey(m, key) & mask;; i = (i + 1) & mask) {
        Entry *entry = &m->entries[i];
        if (entry->state == 0) return NULL;
        if (entry->state == 1 && keysEqual(m, entry->key, key)) return entry;
    }
}

static void growMap(CplMap *m) {
    Entry *old = m->entries;
    int64_t oldCapacity = m->capacity;

    // only grow when the live entries need it; otherwise just clear out deleted slots
    if ((m->size + 1) * 2 > m->capacity) m->capacity *= 2;
    m->entries = arenaAlloc(sizeof(Entry) * (size_t)m->capacity);
    m->deleted = 0;

    uint64_t mask = (uint64_t)m->capacity - 1;
    for (int64_t i = 0; i < oldCapacity; i++) {
        if (old[i].state != 1) continue;
        uint64_t j = hashKey(m, old[i].key) & mask;
        while (m->entries[j].state != 0) j = (j + 1) & mask;
        m->entries[j] = old[i];
    }
}

// returns a pointer to the 8 byte value slot, inserting a zeroed one if needed
char *cpl_map_at(CplMap *m, uint64_t key, int8_t *inserted) {
    key = normalizeKey(m, key);
    Entry *entry = findEntry(m, key);
    if (entry != NULL) {
        *inserted = 0;
        return (char *)&entry->value;
    }

    if ((m->size + m->deleted + 1) * 4 > m->capacity * 3) growMap(m);

    uint64_t mask = (uint64_t)m->capacity - 1;
    uint64_t i = hashKey(m, key) & mask;
    while (m->entries[i].state == 1) i = (i + 1) & mask;
    if (m->entries[i].state == 2) m->deleted--;

    m->entries[i].state = 1;
    m->entries[i].key = key;
    m->entries[i].value = 0;
    m->size++;
    *inserted = 1;
    return (char *)&m->entries[i].value;
}

int8_t cpl_map_has(CplMap *m, uint64_t key) { return findEntry(m, normalizeKey(m, key)) != NULL; }

void cpl_map_del(CplMap *m, uint64_t key) {
    Entry *entry = findEntry(m, normalizeKey(m, key));
    if (entry == NULL) return;
    entry->state = 2;
    m->size--;
    m->deleted++;
}

int64_t cpl_map_size(CplMap *m) { return m->size; }

void cpl_map_clear(CplMap *m) {
    memset(m->entries, 0, sizeof(Entry) * (size_t)m->capacity);
    m->size = 0;
    m->deleted = 0;
}

// all keys in sorted order, as a vector with elements of elemSize bytes
CplVec *cpl_map_keys(CplMap *m, int64_t elemSize) {
    CplVec *keys = cpl_vec_new(8, m->size);
    int64_t count = 0;
    for (int64_t i = 0; i < m->capacity; i++) {
        if (m->entries[i].state == 1) memcpy(keys->data + 8 * count++, &m->entries[i].key, 8);
    }
    sortRaw(keys->data, count, 8, m->kind);

    // narrow to the key type's size (little endian, so the low bytes come first)
    if (elemSize != 8) {
        for (int64_t i = 0; i < count; i++) memmove(keys->data + i * elemSize, keys->data + i * 8, (size_t)elemSize);
        keys->elemSize = elemSize;
        keys->cap = (keys->cap * 8) / elemSize;
    }
    return keys;
}
// endregion

// region program start
// The program runs on its own thread with a huge stack (a quarter of the machine's memory, up to
// 16 GB), so a DFS ten million levels deep is fine. The stack is a MAP_NORESERVE reservation, so
// only the part that's actually used costs memory. Below it sits a guard region; touching it means
// the recursion went too far, which is reported instead of crashing. The cap keeps a runaway
// recursion from eating all memory before it gets there.
typedef int32_t (*CplEntry)(void);

#define MAX_STACK ((size_t)16 << 30)
#define MIN_STACK ((size_t)64 << 20)
#define GUARD_SIZE ((size_t)1 << 20)

static CplEntry entryFunction;
static int32_t exitCode;
static char *stackLow = NULL;
static char *stackGuardEnd = NULL;
static char alternateStack[1 << 16];

static void onSegfault(int signalNumber, siginfo_t *info, void *context) {
    (void)signalNumber;
    (void)context;
    char *address = info->si_addr;
    cpl_flush();
    // a frame bigger than the guard can land below it, so anything near the stack counts
    if (stackLow != NULL && address < stackGuardEnd && address + MIN_STACK >= stackLow) {
        const char message[] = "~~~ RUNTIME ERROR: stack overflow (the recursion is too deep, or never stops)\n";
        writeAll(2, message, sizeof(message) - 1);
    } else {
        const char message[] = "~~~ RUNTIME ERROR: segmentation fault\n";
        writeAll(2, message, sizeof(message) - 1);
    }
    _exit(1);
}

static void *runEntry(void *argument) {
    (void)argument;
    // the signal handler needs a stack of its own, since the overflowing one is unusable
    stack_t alternate = {.ss_sp = alternateStack, .ss_size = sizeof(alternateStack), .ss_flags = 0};
    sigaltstack(&alternate, NULL);
    exitCode = entryFunction();
    return NULL;
}

int32_t cpl_start(CplEntry entry) {
    entryFunction = entry;

    void *stack = MAP_FAILED;
    size_t size = MAX_STACK;
    long pages = sysconf(_SC_PHYS_PAGES), pageSize = sysconf(_SC_PAGESIZE);
    if (pages > 0 && pageSize > 0 && (size_t)pages * (size_t)pageSize / 4 < size) {
        size = (size_t)pages * (size_t)pageSize / 4;
    }
    // under an address space limit, leave most of it to the arena
    size_t limit = addressSpaceLimit();
    if (limit && limit / 4 < size) size = limit / 4;
    if (pageSize > 0) size &= ~(size_t)(pageSize - 1);
    for (; size >= MIN_STACK; size /= 2) {
        stack = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE | MAP_STACK, -1, 0);
        if (stack != MAP_FAILED) break;
    }
    if (stack == MAP_FAILED) return entry();

    mprotect(stack, GUARD_SIZE, PROT_NONE);
    stackLow = stack;
    stackGuardEnd = (char *)stack + GUARD_SIZE;

    struct sigaction action, previous;
    memset(&action, 0, sizeof(action));
    action.sa_sigaction = onSegfault;
    action.sa_flags = SA_SIGINFO | SA_ONSTACK;
    sigemptyset(&action.sa_mask);
    sigaction(SIGSEGV, &action, &previous);

    pthread_attr_t attributes;
    pthread_t thread;
    pthread_attr_init(&attributes);
    int failed = pthread_attr_setstack(&attributes, stack, size) != 0 ||
                 pthread_create(&thread, &attributes, runEntry, NULL) != 0;
    pthread_attr_destroy(&attributes);
    if (failed) {
        sigaction(SIGSEGV, &previous, NULL);
        return entry();
    }
    pthread_join(thread, NULL);

    // when running inside the JIT, leave the host process the way we found it
    sigaction(SIGSEGV, &previous, NULL);
    munmap(stack, size);
    stackLow = stackGuardEnd = NULL;
    return exitCode;
}
// endregion
