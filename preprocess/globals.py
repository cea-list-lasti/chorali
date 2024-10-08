"""
global paths for shared use
change the ROOT to your installation directory
"""
import os

# ROOT = os.path.realpath(os.path.dirname(sys.argv[0])) + '/../'
ROOT = os.environ['ICSISUMM']

DATA_ROOT = os.path.join(ROOT, 'data/')
TOOLS_ROOT = os.path.join(ROOT, 'tools/')
STATIC_DATA_ROOT = DATA_ROOT

STOPWORDS = os.path.join(DATA_ROOT, 'stopwords.english')
ILP_SOLVER = os.path.join(TOOLS_ROOT, 'solver/glpk-4.43/glpsol')
GENETIC_SUMMARIZER = os.path.join(TOOLS_ROOT,
                                  'genetic/greedy_concept_summarizer')
BERKELEY_PARSER_CMD = '%s/parser_bin/distribute.sh %s/parser_bin/berkeleyParser+Postagger.sh' % (TOOLS_ROOT, TOOLS_ROOT)
BOOSTING_LEARNER = '%s/boost/icsiboost' % TOOLS_ROOT
ROUGE_SCORER = os.path.join(ROOT, 'scoring/ROUGE-1.5.5/ROUGE-1.5.5_faster.pl')


def unit_test():

    python_test = True
    try:
        True
    except Exception:
        python_test = False

    nltk_test = True
    try:
        import nltk
        import nltk.stem.porter
        import nltk.tokenize.punkt

    except Exception:
        nltk_test = False

    print('--- Testing for required components ---')
    print('ROOT              [%s]' % ROOT)
    print('STATIC_DATA_ROOT  [%s] exists? [%s]' % (STATIC_DATA_ROOT,
                                                   os.path.exists(
                                                       STATIC_DATA_ROOT)))
    print('ILP_SOLVER        [%s] exists? [%s]' % (ILP_SOLVER,
                                                   os.path.exists(ILP_SOLVER)))
    print('ROUGE_SCORER      [%s] exists? [%s]' % (ROUGE_SCORER,
                                                   os.path.exists(
                                                       ROUGE_SCORER)))
    print('Python version 2.5? [%s]' % python_test)
    print('NLTK exists? [%s]' % nltk_test)
    print('-------------------------------')


if __name__ == '__main__':
    """
    make sure all paths exist
    """
    unit_test()
