// I/O for the C++ reference solutions. Built with -DFAST_IO it's a buffered reader and writer
// equivalent to CPL's runtime (so both sides pay the same for I/O); without it, it's the
// cin/cout with sync_with_stdio(false) that most competitive programmers use.
#pragma once
#include <bits/stdc++.h>
#include <unistd.h>

#ifdef FAST_IO
namespace io {
static char inBuffer[1 << 16];
static size_t inLength = 0, inPosition = 0;
static char outBuffer[1 << 20];
static size_t outLength = 0;

inline int peekChar() {
    if (inPosition == inLength) {
        ssize_t count = read(0, inBuffer, sizeof(inBuffer));
        if (count <= 0) return -1;
        inLength = (size_t)count;
        inPosition = 0;
    }
    return (unsigned char)inBuffer[inPosition];
}
inline void skipSpaces() {
    int c;
    while ((c = peekChar()) == ' ' || c == '\n' || c == '\r' || c == '\t') inPosition++;
}
inline long long readLong() {
    skipSpaces();
    bool negative = false;
    if (peekChar() == '-') { negative = true; inPosition++; }
    long long value = 0;
    int c;
    while ((c = peekChar()) >= '0' && c <= '9') { value = value * 10 + (c - '0'); inPosition++; }
    return negative ? -value : value;
}
inline int readInt() { return (int)readLong(); }
inline std::string readWord() {
    skipSpaces();
    std::string word;
    int c;
    while ((c = peekChar()) > ' ') { word.push_back((char)c); inPosition++; }
    return word;
}
inline void flush() {
    size_t offset = 0;
    while (offset < outLength) {
        ssize_t written = write(1, outBuffer + offset, outLength - offset);
        if (written <= 0) break;
        offset += (size_t)written;
    }
    outLength = 0;
}
inline void writeChar(char c) {
    if (outLength == sizeof(outBuffer)) flush();
    outBuffer[outLength++] = c;
}
inline void writeLong(long long value) {
    if (outLength + 24 > sizeof(outBuffer)) flush();
    unsigned long long magnitude = value < 0 ? 0ULL - (unsigned long long)value : (unsigned long long)value;
    if (value < 0) outBuffer[outLength++] = '-';
    char digits[24];
    int count = 0;
    do { digits[count++] = (char)('0' + magnitude % 10); magnitude /= 10; } while (magnitude);
    while (count) outBuffer[outLength++] = digits[--count];
}
inline void writeString(const std::string &s) { for (char c : s) writeChar(c); }
struct Flusher { ~Flusher() { flush(); } } flusher;
inline void setup() {}
}  // namespace io
#else
namespace io {
inline void setup() { std::ios::sync_with_stdio(false); std::cin.tie(nullptr); }
inline long long readLong() { long long value; std::cin >> value; return value; }
inline int readInt() { int value; std::cin >> value; return value; }
inline std::string readWord() { std::string word; std::cin >> word; return word; }
inline void writeChar(char c) { std::cout.put(c); }
inline void writeLong(long long value) { std::cout << value; }
inline void writeString(const std::string &s) { std::cout << s; }
inline void flush() { std::cout.flush(); }
}  // namespace io
#endif
