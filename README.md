# Smart Money System – mobil / browser

Samme regler som den originale app, men **uden MetaTrader 5 og uden Windows**.
Du åbner den i telefonens browser.

## Det jeg IKKE kan gøre for dig

- Logge ind på din broker
- Holde MT5 kørende 24/7
- Lægge rigtige handler
- Hoste en privat server i dit navn uden din konto (Streamlit Cloud er gratis og din)

## 5 minutter på telefon + computer første gang

### A. Gratis hosting (bedst til telefon)

1. Opret konto på https://github.com og https://share.streamlit.io
2. Upload mappen `smart-money-mobile` som et GitHub-repo
3. På Streamlit Cloud: **New app** → vælg repoet → Main file `app.py`
4. Når den er live, får du et link ala `https://xxx.streamlit.app`
5. Åbn linket på telefonen. Sæt det på hjemmeskærmen.

### B. Kør på en PC/Mac, se på telefonen

```bash
cd smart-money-mobile
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

I terminalen står en **Network URL** (`http://192.168.x.x:8501`).
Telefon og computer på samme Wi-Fi → åbn den adresse på telefonen.

## Data

- **Yahoo Finance** giver ~2 måneder 15-min guld (GC=F). Det er forsinket og ikke din brokers pris.
- **CSV** (`time,open,high,low,close`) til længere backtest, fx eksport fra MT5 på en PC.

## Signaler

Location → Liquidity → Sweep → Displacement → BOS.
Appen handler ikke. Du taster selv i din brokers mobilapp.
