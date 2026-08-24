#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ -z "${LOGISIM_JAR:-}" || ! -f "$LOGISIM_JAR" ]]; then
  echo "Set LOGISIM_JAR to logisim-evolution-4.1.0-all.jar" >&2
  exit 2
fi

java_home_bin="${JAVA_HOME:+$JAVA_HOME/bin}"
java_cmd="${java_home_bin:+$java_home_bin/}java"
javac_cmd="${java_home_bin:+$java_home_bin/}javac"

python3 hardware7400/generate.py
python3 hardware7400/validate_structure.py

mkdir -p build/7400-java build/7400-prefs
"$javac_cmd" -cp "$LOGISIM_JAR" -d build/7400-java hardware7400/tools/HeadlessLogisimTest.java
classpath="$LOGISIM_JAR:build/7400-java"
java_options=(-Djava.awt.headless=true -Djava.util.prefs.userRoot="$repo_root/build/7400-prefs")

run_vector() {
  "$java_cmd" "${java_options[@]}" -cp "$classpath" HeadlessLogisimTest \
    "ЭВМ-7400.circ" "$1" "hardware7400/tests/$2"
}

run_vector ALU8_74xx alu.txt
run_vector ControlStore_28C64 control.txt
run_vector FFTest_7474 ff.txt
run_vector Register8_74xx register.txt
run_vector PC8_74xx pc.txt
run_vector CPU7400_Core cpu.txt
