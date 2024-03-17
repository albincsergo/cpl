#/bin/bash

# This script should be used to build the project
if [ "$1" = "--setup" ]
then
    mkdir build
    cmake -S . -B build
    cmake --build build
else
    cmake --build build
fi