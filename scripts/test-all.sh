#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -z "${LOGISIM_JAR:-}" || ! -f "$LOGISIM_JAR" ]]; then
  echo "Set LOGISIM_JAR to logisim-evolution-4.1.0-all.jar" >&2
  exit 2
fi

python3 hardware/generate.py
python3 -m unittest discover -s tests -v

mkdir -p build/java build/prefs
javac -cp "$LOGISIM_JAR" -d build/java tools/HeadlessLogisimTest.java
classpath="$LOGISIM_JAR:build/java"
project=hardware/MT16-Barrel-PC.circ
java_options=(-Djava.awt.headless=true -Djava.util.prefs.userRoot="$repo_root/build/prefs")

java "${java_options[@]}" -cp "$classpath" HeadlessLogisimTest "$project" ALU16 hardware/tests/alu.txt
java "${java_options[@]}" -cp "$classpath" HeadlessLogisimTest "$project" MicrocodeControl hardware/tests/microcode.txt
java "${java_options[@]}" -cp "$classpath" HeadlessLogisimTest "$project" Scheduler4 hardware/tests/scheduler.txt
java "${java_options[@]}" -cp "$classpath" HeadlessLogisimTest "$project" MT16_Computer hardware/tests/demo.txt
