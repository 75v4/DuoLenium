# DuoLenium (updated)

Selenium bot that completes a Duolingo practice session to keep your streak.
Automating Duolingo is against its terms of service; use a spare account at your own risk.

## Windows / Mac / Linux
    pip install -r requirements.txt
    python main.py

## Termux (Android)
    bash setup_termux.sh
    bash run.sh

## GitHub Actions (daily, free)
Repo > Settings > Secrets and variables > Actions: add `DUO_EMAIL`, `DUO_PASSWORD`, `DUO_LANG` (e.g. `french`).
Then Actions tab > "Duolingo streak" > Run workflow.

Env vars: `DUO_BROWSER` (chrome|firefox), `DUO_HEADLESS` (1), `CHROMEDRIVER`, `CHROME_BIN`, `GECKODRIVER`.
