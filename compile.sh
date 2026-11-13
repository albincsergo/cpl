#!/bin/bash

# This script runs the compiler and executes the generated IR
./build/cpl
cat a.ll
lli a.ll
printf "\n"
echo $?