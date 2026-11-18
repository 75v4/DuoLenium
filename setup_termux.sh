#!/data/data/com.termux/files/usr/bin/bash
# One-time setup for Termux (Android). Uses headless Firefox + geckodriver.
set -e
pkg install -y x11-repo
pkg upgrade -y
pkg install -y python firefox geckodriver git
pip install -r requirements.txt
echo
echo "Setup done. Run:  bash run.sh"
