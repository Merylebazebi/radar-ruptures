#!/usr/bin/env bash
# Pipeline quotidien : ingestion -> chargement -> transformation + tests qualité.
# Lancé par cron. Chaque étape est idempotente : relancer le pipeline plusieurs
# fois par jour ne crée ni doublon ni retéléchargement.
#
# Les étapes s'enchaînent même si l'une échoue : si un fichier du référentiel
# n'a pas pu être téléchargé, les autres sont quand même chargés, et le
# lancement suivant rattrapera ce qui manque. Le code de sortie vaut 1 si au
# moins une étape a échoué.

cd "$(dirname "$0")/.." || exit 1
PYTHON=".venv/bin/python"
mkdir -p logs
LOG=logs/pipeline.log
STATUT=0

echo "===== $(date '+%Y-%m-%d %H:%M:%S') début du pipeline" >> $LOG
for etape in ingestion chargement transformation; do
    if ! $PYTHON src/$etape.py >> $LOG 2>&1; then
        echo "ÉCHEC : $etape" >> $LOG
        STATUT=1
    fi
done
echo "===== $(date '+%Y-%m-%d %H:%M:%S') fin du pipeline (statut $STATUT)" >> $LOG
exit $STATUT
