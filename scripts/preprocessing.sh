#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

set -o functrace
failure()
{
  local lineno=$1
  local msg=$2
  echo "Failed at $0, line $lineno: $msg"
}
trap 'failure ${LINENO} "$BASH_COMMAND"' ERR



DOCS=${TAC}/data/UpdateSumm${TAC_NUMBER}_test_docs_files/
REF=${TAC}/results/UpdateSumm${TAC_NUMBER}_eval/ROUGE/models/
OUTPUT=${ICSISUMM}/output/u${TAC_NUMBER}/

echo "summarize.sh. Will write to ${OUTPUT}"

PYTHONPATH=${PYTHONPATH:-}
export PYTHONPATH=${ICSISUMM}/nltk/nltk-0.9.2:${ICSISUMM}/preprocess/splitta:$PYTHONPATH
PATH=${PATH:-}
export PATH=${ICSISUMM}/solver/glpk-4.43/examples/:$PATH

install -d $OUTPUT

# Preprocessing
python ${ICSISUMM}/preprocess/main.py --output $OUTPUT --docpath $DOCS --manpath $REF --task u${TAC_NUMBER} --reload --splitta-model ${ICSISUMM}/preprocess/splitta/model_nb/ 1>&2

install -d ${DATA}/20${TAC_NUMBER}/source_alpha_lines_icsi
cp  $OUTPUT/*-A.sent ${DATA}/20${TAC_NUMBER}/source_alpha_lines_icsi
install -d ${DATA}/20${TAC_NUMBER}/source_alpha_lines_icsi_B
cp  $OUTPUT/*-B.sent ${DATA}/20${TAC_NUMBER}/source_alpha_lines_icsi_B

echo "Sentence splitting DONE"  1>&2

# Tokenization
for i in $OUTPUT/*.sent ; do
  echo "Tokenizing $OUTPUT/*.sent" 1>&2
  ${ICSISUMM}/preprocess/penn_treebank_tokenizer.sed $i > $i.tok  
done
echo "Tokenization DONE" 1>&2

