#!/usr/bin/env bash
# Publie les CSV de web/ sur GitHub : Streamlit Community Cloud redéploie l'app
# automatiquement à chaque push. Ne fait rien si les données n'ont pas changé.
cd "$(dirname "$0")/.." || exit 1
.venv/bin/python src/export_web.py || exit 1
git add web/alertes.csv web/historique.csv
if git diff --cached --quiet; then
    echo "Rien de nouveau à publier"
    exit 0
fi
git commit -m "Données du tableau de bord du $(date +%Y-%m-%d)" -- web/alertes.csv web/historique.csv && git push
