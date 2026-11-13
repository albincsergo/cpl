// CPL runtime library.
//
// Compiled programs call into this file for everything that is too
// annoying to write in raw LLVM IR: strings, vectors, maps, buffered
// input/output and runtime errors. Memory is never freed - CPL programs
// are short-lived, just like the competitive programming solutions they
// make fun of.

#include <errno.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef struct {
    int64_t len;
    char data[];
} CplStr;

typedef struct {
    int64_t len;
    int64_t cap;
    int64_t elemSize;
    char *data;
} CplVec;

// key kinds shared by maps and sorting
enum { KIND_SIGNED = 0, KIND_UNSIGNED = 1, KIND_DOUBLE = 2, KIND_STRING = 3 };

// region output
static char outBuffer[1 << 16];
static size_t outLength = 0;

void cpl_flush(void) {
    size_t offset = 0;
    while (offset < outLength) {
        ssize_t written = write(1, outBuffer + offset, outLength - offset);
        if (written <= 0) {
            if (written < 0 && errno == EINTR) continue;
            break;
        }
        offset += (size_t)written;
    }
    outLength = 0;
}

static void outWrite(const char *data, size_t length) {
    if (outLength + length > sizeof(outBuffer)) {
        cpl_flush();
        if (length > sizeof(outBuffer)) {
            size_t offset = 0;
            while (offset < length) {
                ssize_t written = write(1, data + offset, length - offset);
                if (written <= 0) {
                    if (written < 0 && errno == EINTR) continue;
                    return;
                }
                offset += (size_t)written;
            }
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

void cpl_print_str(CplStr *s) {
    if (s != NULL) outWrite(s->data, (size_t)s->len);
}
// endregion

// region errors
__attribute__((noreturn)) static void panic(const char *format, ...) {
    cpl_flush();
    va_list args;
    va_start(args, format);
    fprintf(stderr, "~~~ RUNTIME ERROR: ");
    vfprintf(stderr, format, args);
    fprintf(stderr, "\n");
    va_end(args);
    fflush(stderr);
    exit(1);
}

void cpl_panic_index(int64_t index, int64_t length) {
    panic("index %lld is out of bounds for length %lld", (long long)index, (long long)length);
}

void cpl_panic_div(void) { panic("division by zero"); }

void cpl_panic_nil(void) { panic("accessed a field of nil"); }

void cpl_panic_empty(void) { panic("vector is empty"); }

static void *checkedAlloc(size_t size) {
    void *memory = calloc(1, size > 0 ? size : 1);
    if (memory == NULL) panic("out of memory");
    return memory;
}

static void *checkedRealloc(void *memory, size_t size) {
    void *result = realloc(memory, size > 0 ? size : 1);
    if (result == NULL) panic("out of memory");
    return result;
}

void *cpl_alloc(int64_t size) { return checkedAlloc((size_t)size); }
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

static CplStr *strNew(int64_t length) {
    CplStr *s = checkedAlloc(sizeof(CplStr) + (size_t)length + 1);
    s->len = length;
    s->data[length] = '\0';
    return s;
}

// reads the next whitespace separated word
static char *readWord(size_t *lengthOut) {
    static char *word = NULL;
    static size_t capacity = 0;
    size_t length = 0;

    skipSpaces();
    int c;
    while ((c = peekChar()) >= 0 && !isSpace(c)) {
        if (length + 1 >= capacity) {
            capacity = capacity ? capacity * 2 : 64;
            word = checkedRealloc(word, capacity);
        }
        word[length++] = (char)c;
        inPosition++;
    }
    if (word == NULL) {
        capacity = 64;
        word = checkedAlloc(capacity);
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
    CplStr *s = strNew((int64_t)length);
    memcpy(s->data, word, length);
    return s;
}

// reads the rest of the current line, without the line break
CplStr *cpl_read_line(void) {
    size_t capacity = 64, length = 0;
    char *line = checkedAlloc(capacity);
    int c;
    while ((c = nextChar()) >= 0 && c != '\n') {
        if (length + 1 >= capacity) {
            capacity *= 2;
            line = checkedRealloc(line, capacity);
        }
        line[length++] = (char)c;
    }
    if (length > 0 && line[length - 1] == '\r') length--;

    CplStr *s = strNew((int64_t)length);
    memcpy(s->data, line, length);
    free(line);
    return s;
}
// endregion

// region strings
// a nil string pointer is treated as the empty string everywhere
int64_t cpl_str_len(CplStr *s) { return s ? s->len : 0; }

CplStr *cpl_str_concat(CplStr *a, CplStr *b) {
    int64_t lengthA = cpl_str_len(a), lengthB = cpl_str_len(b);
    CplStr *s = strNew(lengthA + lengthB);
    if (lengthA) memcpy(s->data, a->data, (size_t)lengthA);
    if (lengthB) memcpy(s->data + lengthA, b->data, (size_t)lengthB);
    return s;
}

int32_t cpl_str_cmp(CplStr *a, CplStr *b) {
    int64_t lengthA = cpl_str_len(a), lengthB = cpl_str_len(b);
    int64_t shorter = lengthA < lengthB ? lengthA : lengthB;
    int result = shorter ? memcmp(a->data, b->data, (size_t)shorter) : 0;
    if (result != 0) return result < 0 ? -1 : 1;
    return lengthA < lengthB ? -1 : (lengthA > lengthB ? 1 : 0);
}

int8_t cpl_str_at(CplStr *s, int64_t index) {
    int64_t length = cpl_str_len(s);
    if (index < 0 || index >= length) cpl_panic_index(index, length);
    return (int8_t)s->data[index];
}

CplStr *cpl_str_sub(CplStr *s, int64_t start, int64_t count) {
    int64_t length = cpl_str_len(s);
    if (start < 0 || start > length) cpl_panic_index(start, length);
    if (count < 0) panic("substring length can't be negative");
    if (count > length - start) count = length - start;

    CplStr *result = strNew(count);
    if (count) memcpy(result->data, s->data + start, (size_t)count);
    return result;
}

CplStr *cpl_str_from_char(int8_t c) {
    CplStr *s = strNew(1);
    s->data[0] = (char)c;
    return s;
}

CplStr *cpl_str_from_i64(int64_t value) {
    char buffer[32];
    int length = snprintf(buffer, sizeof(buffer), "%lld", (long long)value);
    CplStr *s = strNew(length);
    memcpy(s->data, buffer, (size_t)length);
    return s;
}

CplStr *cpl_str_from_u64(uint64_t value) {
    char buffer[32];
    int length = snprintf(buffer, sizeof(buffer), "%llu", (unsigned long long)value);
    CplStr *s = strNew(length);
    memcpy(s->data, buffer, (size_t)length);
    return s;
}

CplStr *cpl_str_from_f64(double value) {
    char buffer[64];
    int length = snprintf(buffer, sizeof(buffer), "%g", value);
    CplStr *s = strNew(length);
    memcpy(s->data, buffer, (size_t)length);
    return s;
}

CplStr *cpl_str_from_bool(int8_t value) {
    const char *text = value ? "true" : "false";
    int64_t length = (int64_t)strlen(text);
    CplStr *s = strNew(length);
    memcpy(s->data, text, (size_t)length);
    return s;
}

// fixed number of digits after the decimal point, like cout << fixed << setprecision(d)
CplStr *cpl_str_prec(double value, int64_t digits) {
    if (digits < 0) digits = 0;
    if (digits > 100) digits = 100;
    int length = snprintf(NULL, 0, "%.*f", (int)digits, value);
    CplStr *s = strNew(length);
    snprintf(s->data, (size_t)length + 1, "%.*f", (int)digits, value);
    return s;
}

int64_t cpl_str_to_i64(CplStr *s) {
    if (cpl_str_len(s) == 0) panic("can't convert an empty string to an integer");
    char *end;
    errno = 0;
    long long value = strtoll(s->data, &end, 10);
    if (*end != '\0' || errno != 0) panic("can't convert \"%s\" to an integer", s->data);
    return (int64_t)value;
}

double cpl_str_to_f64(CplStr *s) {
    if (cpl_str_len(s) == 0) panic("can't convert an empty string to a number");
    char *end;
    double value = strtod(s->data, &end);
    if (*end != '\0') panic("can't convert \"%s\" to a number", s->data);
    return value;
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

static void sortRaw(char *data, int64_t count, int64_t elemSize, int32_t kind) {
    if (count < 2) return;
    sortKind = kind;
    sortSize = elemSize;
    qsort(data, (size_t)count, (size_t)elemSize, compareElements);
}
// endregion

// region vectors
CplVec *cpl_vec_new(int64_t elemSize, int64_t length) {
    if (length < 0) panic("vector size can't be negative (got %lld)", (long long)length);
    CplVec *v = checkedAlloc(sizeof(CplVec));
    v->elemSize = elemSize;
    v->len = length;
    v->cap = length;
    v->data = length > 0 ? checkedAlloc((size_t)(length * elemSize)) : NULL;
    return v;
}

// appends a zeroed element and returns a pointer to it
char *cpl_vec_push(CplVec *v) {
    if (v->len == v->cap) {
        int64_t capacity = v->cap ? v->cap * 2 : 4;
        v->data = checkedRealloc(v->data, (size_t)(capacity * v->elemSize));
        v->cap = capacity;
    }
    char *slot = v->data + v->len * v->elemSize;
    memset(slot, 0, (size_t)v->elemSize);
    v->len++;
    return slot;
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
        for (int64_t i = 0; i < cpl_str_len(s); i++) hash = (hash ^ (uint8_t)s->data[i]) * 1099511628211ULL;
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
    if (m->kind == KIND_STRING) return cpl_str_cmp((CplStr *)(uintptr_t)a, (CplStr *)(uintptr_t)b) == 0;
    return a == b;
}

CplMap *cpl_map_new(int32_t kind) {
    CplMap *m = checkedAlloc(sizeof(CplMap));
    m->kind = kind;
    m->capacity = 16;
    m->entries = checkedAlloc(sizeof(Entry) * (size_t)m->capacity);
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
    m->entries = checkedAlloc(sizeof(Entry) * (size_t)m->capacity);
    m->deleted = 0;

    uint64_t mask = (uint64_t)m->capacity - 1;
    for (int64_t i = 0; i < oldCapacity; i++) {
        if (old[i].state != 1) continue;
        uint64_t j = hashKey(m, old[i].key) & mask;
        while (m->entries[j].state != 0) j = (j + 1) & mask;
        m->entries[j] = old[i];
    }
    free(old);
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
