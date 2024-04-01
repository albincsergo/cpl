#/bin/bash

# This script should be used to build the project
./build/cpl
cat a.ll
lli a.ll
printf "\n"
echo $?