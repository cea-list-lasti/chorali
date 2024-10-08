import os, sys, re, math, util, ilp, text, treenode, prob_util
from operator import itemgetter  # for sorting dictionaries by value
from globals import *

class Mapper:
    """
    self.problem             a SummaryProblem instance
    self.unit_selector       retrieve sub-sentence units (eg. ngrams)
        n1: word unigrams
        n2: word bigrams (DEFAULT)
        su4: skip bigrams (max. gap of 4) + unigrams
    """

    def __init__(self, summary_problem, units='n2'):

        self.unit_name = units
        self.problem = summary_problem

        if   units == 'n1': self.unit_selector = lambda x: util.get_ngrams(x, n=1)
        elif units == 'n2': self.unit_selector = lambda x: util.get_ngrams(x, n=2)
        elif units == 'n3': self.unit_selector = lambda x: util.get_ngrams(x, n=3)
        elif units == 'n4': self.unit_selector = lambda x: util.get_ngrams(x, n=4)
        elif units == 'su4' : self.unit_selector = lambda x: util.get_skip_bigrams(x, k=4) + util.get_ngrams(x, n=1)
        else: units = util.get_ngrams  # default options

        ## variables to set later
        self.concepts = None
        self.concept_weights = None
        self.concept_index = None
        self.relevant_sents = None
        self.relevant_sent_concepts = None

        ## defaults
        self.min_sent_length = 5
        self.max_sents = 10000

    def map_concepts(self):
        """
        Step 1: map concepts to weights
        assign self_concept_sets
        """
        abstract()

    def choose_sents(self):
        """
        Step 2: choose a subset of the problem sentences based on concepts, etc.
        """
        abstract()

    def run(self, max_length=100, style='ilp'):
        """
        Step 3: create formatted output
        """
        ## make sure step 2 has been completed
        if not self.relevant_sents:
            sys.stderr.write('\nError: need to run choose_sents first\n')
            return None

        output = []
        curr_sents = self.relevant_sents                 # list of sentences
        curr_sent_concepts = self.relevant_sent_concepts # dict of concepts in each sentence {0: [1, 4, ... ], 1: ... }
        curr_concept_weights = self.concept_weights      # dict of weight for each concept {'(he, said)': 3.4, ... }
        curr_concept_index = self.concept_index          # dict of index for each concept  {'(he, said)': 100, ... }

        curr_concept_sents = {}                          # dict of sentences for each concept
        for sent_index in range(len(curr_sents)):
            concepts = curr_sent_concepts[sent_index]
            for concept in concepts:
                if not concept in curr_concept_sents: curr_concept_sents[concept] = []
                curr_concept_sents[concept].append(sent_index)

        ## testing code
        #num_sents = len(curr_sents)
        #num_concepts = len(curr_concept_index)
        #sent_lengths = [len(s.tokens) for s in curr_sents]
        #print
        #print 'sents [%d] concepts [%d]  [%1.2f]' %(num_sents, num_concepts, 1.0*num_concepts/num_sents)
        #print 'avg sent length [%1.2f]' %(1.0*sum(sent_lengths)/len(sent_lengths))
        #print

        ## custom format
        if style != 'ilp':
            ## TODO: this is broken! Add local search solver class
            output.append('%s NUM_SENTENCES %d' %(id, len(curr_sents)))
            output.append('%s NUM_CONCEPTS %d' %(id, len(curr_concept_index)))
            output.append('%s TEXT TOPIC %s %s' %(id, self.problem.title, self.problem.narr))

            ## sentence info
            for sent_index in range(len(curr_sents)):
                output.append('%s LENGTH %d %d' %(id, sent_index, curr_sents[sent_index].length))
                output.append('%s TEXT %d %s' %(id, sent_index, curr_sents[sent_index].original))
                concept_list = ' '.join(map(str, curr_sent_concepts[sent_index]))
                output.append('%s CONCEPTS %d %d %s' %(id, sent_index, len(curr_sent_concepts[sent_index]), concept_list))

            ## concept info
            for concept in curr_concept_weights.keys():
                str_concept = '_'.join(concept)
                concept_weight = curr_concept_weights[concept]
                concept_index = curr_concept_index[concept]
                output.append('%s CONCEPT_INFO %d %1.4f %s' %(id, concept_index, concept_weight, str_concept))

        ## ILP output format used by glpsol (glpk)
        else:
            problem = ilp.IntegerLinearProgram()
            obj = ' + '.join(['%f c%d' %(weight, curr_concept_index[concept]) for concept, weight in curr_concept_weights.items()])
            obj = obj.replace(' + -', ' - ')
            problem.objective["score"] = obj

            s1 = ' + '.join(['%d s%d' %(curr_sents[sent_index].length, sent_index) for sent_index in range(len(curr_sents))])
            s2 = ' <= %s\n' %max_length
            problem.constraints["length"] = s1 + s2

            for concept, concept_index in curr_concept_index.items():
                ## at least one sentence containing a selected bigram must be selected
                s1 = ' + '.join([ 's%d' %sent_index for sent_index in curr_concept_sents[concept_index]])
                s2 = ' - c%d >= 0' %concept_index
                problem.constraints["presence_%d" % concept_index] = s1 + s2

                ## if a bigram is not selected then all sentences containing it are deselected
                s1 = ' + '.join([ 's%d' %sent_index for sent_index in curr_concept_sents[concept_index]])
                s2 = '- %d c%d <= 0' %(len(curr_concept_sents[concept_index]), concept_index)
                problem.constraints["absence_%d" % concept_index] = s1 + s2

            for sent_index in range(len(curr_sents)):
                problem.binary["s%d" % sent_index] = curr_sents[sent_index]
            for concept, concept_index in curr_concept_index.items():
                problem.binary["c%d" % concept_index] = 1

            #problem.debug = 1
            problem.run()
            output = []
            for sent_index in range(len(curr_sents)):
                if problem.output["s%d" % sent_index] == 1:
                    output.append(curr_sents[sent_index])

        return output

class CheatingMapper(Mapper):
    """
    Use human summaries to pick weights
    For Maximum ROUGE experiments
    """

    def map_concepts(self):
        """
        Concepts are weighted according to the number of annotator summaries
        in which they apper.
        """

        ## make sure gold summaries are loaded
        if (not self.problem.annotators) or (not self.problem.training):
            sys.stderr.write('\nError: no gold summaries loaded\n')
            return

        concepts = {}
        for annotator in self.problem.annotators:
            annotator_concepts = {}

            for rawsent in self.problem.training[annotator]:
                sent = text.Sentence(rawsent)
                units = self.unit_selector(sent.stemmed)

                for unit in units:
                    if not unit in annotator_concepts: annotator_concepts[unit] = 0
                    annotator_concepts[unit] += 1

            for concept in annotator_concepts:
                if not concept in concepts: concepts[concept] = 0
                concepts[concept] += 1

        self.concepts = concepts
        return True

    def choose_sents(self):
        """
        """

        ## check that concepts exist
        if not self.concepts:
            sys.stderr.write('\nError: no concepts identified -- use map_concepts first\n')
            return None

        concept_weights = self.concepts
        docset = self.problem.new_docs
        used_concepts = set()
        relevant_sents = []
        sent_concepts = []

        ## get all input sentences
        sents = []
        for doc in docset: sents.extend(doc.sentences)

        ## delete this testing code!
        sents = sents[:self.max_sents]

        for sent in sents:
            ## skip short sentences
            if sent.length < self.min_sent_length: continue

            ## get concepts in this sentence
            units = self.unit_selector(sent.stemmed)

            ## concepts that appear in this sentence
            curr_concepts = set([u for u in units if u in concept_weights])

            ## skip sentences with no concepts
            if len(curr_concepts) == 0: continue

            ## add sentence and its concepts
            relevant_sents.append(sent)
            sent_concepts.append(curr_concepts)
            used_concepts.update(curr_concepts)

        ## create an index for mapping concepts to integers
        concept_weights_final = {}
        concept_index = {}
        index = 0
        for concept in used_concepts:
            concept_index[concept] = index
            concept_weights_final[concept] = concept_weights[concept]
            index += 1
        concept_weights = concept_weights_final

        ## set member variables
        self.concept_weights = concept_weights
        self.concept_index = concept_index
        self.relevant_sents = relevant_sents
        self.relevant_sent_concepts = [[concept_index[c] for c in cs] for cs in sent_concepts]

        return True


class HeuristicMapper(Mapper):
    """
    """

    def map_concepts(self):
        """
        """
        min_count = 3

        ## get document statistics
        concept_sets = []
        sent_count = 0
        used_sents = set()

        doc_set = self.problem.new_docs
        concept_set = {}
        for doc in doc_set:
            #if doc.doctype != 'NEWS STORY': continue
            doc_concepts = {}
            for sent in doc.sentences:

                sent_count += 1

                ## ignore short sentences
                if sent.length < self.min_sent_length: continue

                ## ignore duplicate sentences
                sent_stemmed_str = ' '.join(sent.stemmed)
                if sent_stemmed_str in used_sents: continue
                used_sents.add(sent_stemmed_str)

                ## don't consider sentences with no query overlap
                if self.problem.query:
                    sim = sent.sim_basic(self.problem.query)
                else: sim = 1
                if sim <= 0: continue

                ## testing
                #parse = treenode.TreeNode(sent.parsed)
                #print sent.original
                #for leaf in parse.leaves:
                #    print(' ', leaf.text, leaf.label)

                units = self.unit_selector(sent.stemmed)

                for unit in units:
                    if not unit in doc_concepts: doc_concepts[unit] = 0
                    doc_concepts[unit] += 1

            use_doc_freq = len(doc_set) > min_count

            for concept, count in doc_concepts.items():
                if not concept in concept_set: concept_set[concept] = 0
                if use_doc_freq: concept_set[concept] += 1      # doc frequency
                else: concept_set[concept] += count             # raw frequency

        ## apply a few transformations
        final_concept_set = {}
        num_used_concepts = 0

        sortedItems = concept_set.items()
        sortedItems.sort(key = itemgetter(1), reverse=True)

        for concept, count in sortedItems:
            remove = False

            ## remove low frequency concepts
            if count < min_count: remove = True

            ## remove stop word concepts (word ngrams only!)
            if text.text_processor.is_just_stopwords(concept): remove = True

            ## add to final concept set
            if not remove:
                final_concept_set[concept] = count
                num_used_concepts += 1

        self.concepts = final_concept_set
        return True

    def choose_sents(self):
        """
        """

        ## check that concepts exist
        if not self.concepts:
            sys.stderr.write('\nError: no concepts identified -- use map_concepts first\n')
            return None

        used_sents = set()
        concept_weights = self.concepts
        docset = self.problem.new_docs

        #for doc in self.problem.ir_docs:
        #    if doc.id in [d.id for d in docset]: continue
        #    docset.append(doc)

        used_concepts = set()
        relevant_sents = []
        sent_concepts = []

        sents = []
        ## get all input sentences
        for doc in docset:
            #if doc.doctype != 'NEWS STORY': continue
            sents.extend(doc.sentences)

        ## delete this testing code!
        #sents = sents[:self.max_sents]

        for sent in sents:

            ## ignore short sentences
            if sent.length < self.min_sent_length: continue

            ## ignore duplicate sentences
            sent_stemmed_str = ' '.join(sent.stemmed)
            if sent_stemmed_str in used_sents: continue
            used_sents.add(sent_stemmed_str)

            ## get units
            units = self.unit_selector(sent.stemmed)

            ## concepts that appear in this sentence
            curr_concepts = set([u for u in units if u in concept_weights])

            ## skip sentences with no concepts
            if len(curr_concepts) == 0: continue

            ## add sentence and its concepts
            relevant_sents.append(sent)
            sent_concepts.append(curr_concepts)
            used_concepts.update(curr_concepts)

        ## create an index for mapping concepts to integers
        concept_weights_final = {}
        concept_index = {}
        index = 0
        for concept in used_concepts:
            concept_index[concept] = index
            concept_weights_final[concept] = concept_weights[concept]
            index += 1
        concept_weights = concept_weights_final

        ## set member variables
        self.concept_weights = concept_weights
        self.concept_index = concept_index
        self.relevant_sents = relevant_sents
        self.relevant_sent_concepts = [[concept_index[c] for c in cs] for cs in sent_concepts]

        return True


def map_iterative_docs(docs, unit_selector, query):

    ## initialize uniform doc priors
    doc_values = prob_util.Counter()
    for doc in docs:
        doc_values[doc.docid] = 1
    doc_values = doc_values.makeProbDist()

    ## get units in each doc
    doc_units = {}
    used_sents = set()
    for doc in docs:
        doc_units[doc.docid] = prob_util.Counter()
        for sent in doc.sentences:

            if query:
                sim = sent.sim_basic(query)
            else: sim = 1
            if sim <= 0: continue

            units = unit_selector(sent.stemmed)
            for unit in units:
                if text.text_processor.is_just_stopwords(unit): continue

                doc_units[doc.docid][unit] += 1

    ## repeat until convergence
    for iter in range(1, 51):
        prev_doc_values = doc_values.copy()

        ## get unit values from doc values
        unit_values = prob_util.Counter()
        for doc in doc_units:
            for unit in doc_units[doc]:
                unit_values[unit] += doc_values[doc]
        unit_values = unit_values.makeProbDist()

        ## get doc values from unit values
        doc_values = prob_util.Counter()
        for doc in doc_units:
            for unit in doc_units[doc]:
                doc_values[doc] += unit_values[unit] / len(doc_units[doc])
                #print '%d, %s %1.4f %d' %(iter, unit, unit_values[unit], len(doc_units[doc]))
        doc_values = doc_values.makeProbDist()

        #prob_util.Counter(unit_values).displaySorted(N=5)
        #prob_util.Counter(doc_values).displaySorted(N=10)

        ## check for convergence
        if iter == 1: break
        dist = prob_util.euclidianDistance(prev_doc_values, doc_values)
        print('dist [%1.6f]' %dist)
        if dist < 0.0001: break

    #sys.exit()

    return prob_util.Counter(unit_values), prob_util.Counter(doc_values)


def map_iterative_sents(docs, unit_selector, query):

    ## get sentence set
    sents = []
    for doc in docs:
        for sent in doc.sentences:
            ## skip short sentences
            #if sent.length <= 5: continue

            ## skip sentences with no query overlap
            if query: sim = sent.sim_basic(query)
            else: sim = 1
            if sim <= 0: continue

            sents.append(sent)

    ## initialize uniform sentence priors
    sent_values = prob_util.Counter()
    for sent in sents:
        sent_values[sent.original] = 1
    sent_values = sent_values.makeProbDist()

    ## get units in each sent
    sent_units = {}
    for sent in sents:
        sent_units[sent.original] = prob_util.Counter()
        units = unit_selector(sent.stemmed)
        for unit in units:
            if text.text_processor.is_just_stopwords(unit): continue
            sent_units[sent.original][unit] += 1

    ## repeat until convergence
    for iter in range(1, 51):
        prev_sent_values = sent_values.copy()

        ## get unit values from doc values
        unit_values = prob_util.Counter()
        for sent in sent_units:
            for unit in sent_units[sent]:
                unit_values[unit] += sent_values[sent]
        unit_values = unit_values.makeProbDist()

        ## get sent values from unit values
        sent_values = prob_util.Counter()
        for sent in sent_units:
            for unit in sent_units[sent]:
                sent_values[sent] += unit_values[unit] #/ len(sent_units[sent])
        sent_values = sent_values.makeProbDist()

        #prob_util.Counter(unit_values).displaySorted(N=5)
        #prob_util.Counter(sent_values).displaySorted(N=3)

        ## check for convergence
        entropy_sent = prob_util.entropy(sent_values)
        entropy_unit = prob_util.entropy(unit_values)
        dist = prob_util.klDistance(prev_sent_values, sent_values)
        #print '%d sent entropy [%1.4f]  unit entropy [%1.4f]  sent dist [%1.6f]' %(iter, entropy_sent, entropy_unit, dist)
        if iter == 2: break
        if dist < 0.0001:
            #print '----------------------------'
            break

    return prob_util.Counter(unit_values), prob_util.Counter(sent_values)

def query_expand(docs, unit_selector, query):
    ## get sentence set
    sents = []
    for doc in docs:
        #if doc.doctype != 'NEWS STORY': continue
        for sent in doc.sentences:
            ## skip short sentences
            #if sent.length <= 5: continue
            sents.append(sent)

    ## initialize sentences with query similarity
    sent_values = prob_util.Counter()
    for sent in sents:
        try: sent_values[sent.original] = sent.sim_basic(query) #/ sent.order
        except: sent_values[sent.original] = 1
    sent_values = sent_values.makeProbDist()
    original_sent_values = sent_values.copy()

    ## get units in each sent
    sent_units = {}
    for sent in sents:
        sent_units[sent.original] = prob_util.Counter()
        units = unit_selector(sent.stemmed)
        for unit in units:
            if text.text_processor.is_just_stopwords(unit): continue
            sent_units[sent.original][unit] += 1

    ## repeat until convergence
    prev_unit_entropy = 0
    prev_sent_entropy = 0
    prev_unit_values = {}
    prev_sent_values = {}
    for iter in range(1, 51):
        prev_sent_values = sent_values.copy()

        ## get new unit values from sent values
        unit_values = prob_util.Counter()
        for sent in sent_units:
            for unit in sent_units[sent]:
                unit_values[unit] += sent_values[sent]
        unit_values = unit_values.makeProbDist()

        ## get sent values from unit values
        sent_values = prob_util.Counter()
        for sent in sent_units:
            for unit in sent_units[sent]:
                sent_values[sent] += unit_values[unit] #/ len(sent_units[sent])
        sent_values = sent_values.makeProbDist()

        ## interpolate with original sent weights
        #sent_prior = 0.1
        #for sent in sent_values:
        #    new_value = (sent_prior * original_sent_values[sent]) + ( (1-sent_prior) * sent_values[sent])
        #    #sent_values[sent] = new_value

        #prob_util.Counter(unit_values).displaySorted(N=100)
        #prob_util.Counter(sent_values).displaySorted(N=20)

        ## check for convergence
        entropy_sent = prob_util.entropy(sent_values)
        entropy_unit = prob_util.entropy(unit_values)
        dist = prob_util.klDistance(prev_sent_values, sent_values)
        sys.stderr.write('%d sent entropy [%1.4f]  unit entropy [%1.4f]  sent dist [%1.6f]\n' %(iter, entropy_sent, entropy_unit, dist))

        if iter == 2: break

        #if (entropy_unit >= prev_unit_entropy):  and (entropy_sent >= prev_sent_entropy):
        #    unit_values = prev_unit_values
        #    sent_values = prev_sent_values
        #    break

        prev_unit_entropy = entropy_unit
        prev_sent_entropy = entropy_sent
        prev_unit_values = unit_values
        prev_sent_values = sent_values

        if dist < 0.0001: break

    #prob_util.Counter(unit_values).displaySorted(N=10)
    #prob_util.Counter(sent_values).displaySorted(N=20)

    return prob_util.Counter(unit_values), prob_util.Counter(sent_values)

def get_values(docs, unit_selector, query):

    ## get sentence set
    sents = []
    for doc in docs:
        for sent in doc.sentences:
            sents.append(sent)

    ## initialize sentences with query similarity
    sent_values = prob_util.Counter()
    for sent in sents:
        try: sent_values[sent.original] = sent.sim_basic(query)
        except: sent_values[sent.original] = 1
    #sent_values = sent_values.makeProbDist()
    original_sent_values = sent_values.copy()

    ## get units in each sent and co-occurrences of units
    sent_units = {}
    co_units = prob_util.CondCounter()
    for sent in sents:
        sent_units[sent.original] = prob_util.Counter()
        units = unit_selector(sent.stemmed)
        for unit in units:
            if text.text_processor.is_just_stopwords(unit): continue
            sent_units[sent.original][unit] += 1
            for co_unit in units:
                if unit == co_unit: continue
                co_units[unit][co_unit] += 1

    ## get new unit values from sent values
    unit_values = prob_util.Counter()
    for sent in sent_units:
        for unit in sent_units[sent]:
            #unit_values[unit] += sent_values[sent]
            unit_values[unit] += 1

    ## greedy procedure for removing co-occurrence values
    curr_unit_values = unit_values.copy()
    new_unit_values = prob_util.Counter()
    while True:
        best_unit = curr_unit_values.sortedKeys()[0]
        new_unit_values[best_unit] = curr_unit_values[best_unit]
        print(best_unit, new_unit_values[best_unit])
        curr_unit_values.pop(best_unit)
        for unit in curr_unit_values:
            new_val = curr_unit_values[unit] - co_units[best_unit][unit]
            if new_val > 1: curr_unit_values[unit] = new_val
        if max(curr_unit_values.values()) < 2: break
        if len(new_unit_values) >= 65: break

    unit_values = new_unit_values
    print('--------------',len(unit_values))

    return unit_values, sent_values

    ## get sent values from unit values
    sent_values = prob_util.Counter()
    for sent in sent_units:
        for unit in sent_units[sent]:
            sent_values[sent] += unit_values[unit] #/ len(sent_units[sent])
    sent_values = sent_values.makeProbDist()

def concepts_in_text(sorted_concepts, words):
    c = []
    text = ' ' + ' '.join(words) + ' '
    for concept in sorted_concepts:
        concept_text = ' ' + ' '.join(concept) + ' '
        if concept_text in text:
            c.append(concept)
            text = text.replace(concept_text, ' <MATCHED> ')
            #print '*** [%s] %s' %(concept_text, text)
    return c

def get_overlaps(sent1, sent2):
    """
    find substrings common to both sentences
    """
    matches = []
    s1, s2 = sent1.stemmed, sent2.stemmed
    for i in range(len(s1)):
        for j in range(len(s2)):
            m = 0
            while m<4 and (i+m)<len(s1) and (j+m)<len(s2) and s1[i+m] == s2[j+m]: m+=1
            if m>0:
                matches.append(tuple(s1[i:i+m]))
    return matches

def get_full_concepts(docs, query):
    """
    """
    ## get sentence set
    sents = []
    used_sents = set()
    for doc in docs:
        for sent in doc.sentences:
            ## ignore duplicate sentences
            sent_stemmed_str = ' '.join(sent.stemmed)
            if sent_stemmed_str in used_sents: continue
            used_sents.add(sent_stemmed_str)
            sents.append(sent)

    ngrams = prob_util.Counter()
    for i in range(len(sents)-1):
        for j in range(i+1, len(sents)):
            matches = get_overlaps(sents[i], sents[j])
            for match in matches:
                if text.text_processor.is_just_stopwords(match): continue
                ngrams[match] += 1
                #ngrams[match] += (10 ** (len(match)-1)) / 1000.0

    for ngram, count in ngrams.items():
        if count <= 1: ngrams.pop(ngram)
        else: ngrams[ngram] = (1.0 / 10000) * count * (10 ** len(ngram)-1)

    ngrams.displaySorted(N=40)
    return ngrams

class HeuristicMapperExp(Mapper):
    """
    """

    def map_concepts(self):
        """
        """

        ## get document statistics
        sent_count = 0
        used_sents = set()
        doc_set = self.problem.new_docs
        concept_set, sent_values = query_expand(doc_set, self.unit_selector, self.problem.query)
        #concept_set, sent_values = get_values(doc_set, self.unit_selector, self.problem.query)
        #concept_set = get_full_concepts(doc_set, self.problem.query)

        ## apply a few transformations
        max_concepts = 65
        max_concept_sum = 0.5

        final_concept_set = {}
        num_used_concepts = 0
        concept_sum = 0

        for concept in concept_set.sortedKeys():
            score = concept_set[concept]

            ## don't include more than max_concepts
            if num_used_concepts >= max_concepts: break
            #if score < 2: continue
            #if concept_sum >= max_concept_sum:
            #    print('concepts used: %d' %num_used_concepts)
            #    break

            remove = False

            ## add to final concept set
            if not remove:
                final_concept_set[concept] = score
                num_used_concepts += 1
                concept_sum += score

        self.concepts = final_concept_set
        return True

    def choose_sents(self):
        """
        """

        ## check that concepts exist
        if not self.concepts:
            sys.stderr.write('\nError: no concepts identified -- use map_concepts first\n')
            return None

        used_sents = set()
        concept_weights = self.concepts
        docset = self.problem.new_docs
        used_concepts = set()
        relevant_sents = []
        sent_concepts = []

        sents = []
        for doc in docset:
            #if doc.doctype != 'NEWS STORY': continue
            sents.extend(doc.sentences)

        sorted_concepts = self.concepts.keys()
        #sorted_concepts.sort(cmp=lambda x,y:len(y)-len(x))

        for sent in sents:

            ## ignore short sentences
            if sent.length < self.min_sent_length: continue

            ## ignore duplicate sentences
            sent_stemmed_str = ' '.join(sent.stemmed)
            if sent_stemmed_str in used_sents: continue
            used_sents.add(sent_stemmed_str)

            ## get units
            units = self.unit_selector(sent.stemmed)

            ## concepts that appear in this sentence
            curr_concepts = set([u for u in units if u in concept_weights])
            #curr_concepts = set(concepts_in_text(sorted_concepts, sent.stemmed))

            ## skip sentences with no concepts
            if len(curr_concepts) == 0: continue

            ## add sentence and its concepts
            relevant_sents.append(sent)
            sent_concepts.append(curr_concepts)
            used_concepts.update(curr_concepts)

        ## create an index for mapping concepts to integers
        concept_weights_final = {}
        concept_index = {}
        index = 0
        for concept in used_concepts:
            concept_index[concept] = index
            concept_weights_final[concept] = concept_weights[concept]
            index += 1
        concept_weights = concept_weights_final

        ## set member variables
        self.concept_weights = concept_weights
        self.concept_index = concept_index
        self.relevant_sents = relevant_sents
        self.relevant_sent_concepts = [[concept_index[c] for c in cs] for cs in sent_concepts]

        return True



def setup_features(problem, unit_selector, train=True):

    ## for training, get gold concepts
    gold_concepts = prob_util.Counter()
    if train:
        for annotator in problem.annotators:
            annotator_concepts = {}
            for sent in problem.training[annotator]:
                sentence = text.Sentence(sent)
                units = unit_selector(sentence.stemmed)
                for unit in units:
                    if unit not in annotator_concepts: annotator_concepts[unit] = 0
                    annotator_concepts[unit] += 1
            for concept in annotator_concepts:
                gold_concepts[concept] += 1

    ## get all sentences and unit frequencies
    sents = []
    doc_freq = prob_util.Counter()
    sent_freq = prob_util.Counter()
    raw_freq = prob_util.Counter()
    for doc in problem.new_docs:
        #if doc.doctype != 'NEWS STORY': continue

        doc_counts = prob_util.Counter()
        for sent in doc.sentences:
            sent_counts = prob_util.Counter()
            sents.append(sent)
            for unit in unit_selector(sent.stemmed):
                doc_counts[unit] += 1
                sent_counts[unit] += 1

            for unit in sent_counts:
                sent_freq[unit] += 1

        for unit in doc_counts:
            doc_freq[unit] += 1
            raw_freq[unit] += doc_counts[unit]

    ## get features for each concept unit
    lines = []
    concepts = []

    title = text.Sentence(problem.title)
    narr = text.Sentence(problem.narr)

    for sent in sents:

        ## sentence features
        sentence_sim = sent.sim_basic(problem.query)
        sentence_order = sent.order
        sentence_source = sent.source
        sentence_length = sent.length

        units = unit_selector(sent.stemmed)
        for unit in units:

            ## concept features
            stopword_ratio = 1 - (1.0*len(text.text_processor.remove_stopwords(unit)) / len(unit))
            doc_ratio = 1.0 * doc_freq[unit] / len(problem.new_docs)
            sent_ratio = 1.0 * sent_freq[unit] / len(sents)
            ngram = ' '.join(unit)

            sunit = text.Sentence(ngram)
            title_sim = sunit.sim_basic(title)
            narr_sim = sunit.sim_basic(narr)

            ## output format (boostexter)
            line = '%s, %1.2f, %1.2f, %1.2f, ' %(ngram, doc_ratio, sent_ratio, stopword_ratio)
            line += '%1.2f, %d, %s, %d, ' %(sentence_sim, sentence_order, sentence_source, sentence_length)
            line += '%1.2f, %1.2f, ' %(title_sim, narr_sim)
            if train: line += '%s' %int(gold_concepts[unit]>0)
            else: line += '0'
            line += '.'

            if stopword_ratio == 1: continue

            lines.append(line)
            concepts.append(unit)
            for rep in range(int(gold_concepts[unit]-1)):
                if train:
                    lines.append(line)
                    concepts.append(unit)
    return lines, concepts, doc_freq


class LearningMapper(Mapper):
    """
    """

    def map_concepts(self):
        """
        """
        #do_train = True
        do_train = False

        ## get features in boostexter format
        lines, concepts, concept_freq = setup_features(self.problem, self.unit_selector, train=do_train)

        ## write to file
        filename = '../train/%s.data' %self.problem.id
        fh = open(filename, 'w')
        fh.write('\n'.join(lines)+'\n')
        fh.close()

        if do_train:
            return

        ## classify
        model_stem = '../train/all'
        cmd = '%s -S %s -C < %s' %(BOOSTING_LEARNER, model_stem, filename)
        results = os.popen(cmd).readlines()
        concept_weights = prob_util.Counter()
        all_concept_weights = {}
        for i in range(len(results)):
            score = float(results[i].split()[-1])
            concept_weights[concepts[i]] += score
            if not concepts[i] in all_concept_weights: all_concept_weights[concepts[i]] = []
            all_concept_weights[concepts[i]].append(score)

        #concept_weights.displaySorted(N=1000)

        ## pruning
        final_concept_weights = {}
        count = 0
        for key in concept_weights.sortedKeys()[:300]:
            count += 1
            value = concept_weights[key]
            if value <= 0: break
            final_concept_weights[key] = value

            mean_value = sum(all_concept_weights[key]) / len(all_concept_weights[key])
            final_concept_weights[key] = mean_value * concept_freq[key]
            if count<=10: print(key, mean_value * concept_freq[key])


        print('concepts used: %d' %count)

        self.concept_sets = [final_concept_weights]


    def choose_sents(self):
        """
        """

        ## check that concepts exist
        if not self.concept_sets:
            sys.stderr.write('Error: no concepts identified -- use map_concepts first\n')
            return None

        ## initialize new member variables
        self.concept_weight_sets = []
        self.concept_index_sets = []
        self.relevant_sent_sets = []
        self.relevant_sent_concepts = []

        ## loop over update sets
        for update_set_index in range(len(self.concept_sets)):
            concept_weights = self.concept_sets[update_set_index]
            docset = self.problem.new_docs
            used_sents = set()  # just for pruning duplicates

            sents = []
            for doc in docset:
                #if doc.doctype != 'NEWS STORY': continue
                sents.extend(doc.sentences)
                #sents.extend(doc.paragraphs)

            used_concepts = set()
            relevant_sents = []
            sent_concepts = []

            for sent in sents:

                ## ignore short sentences
                if sent.length < self.min_sent_length: continue

                ## ignore duplicate sentences
                sent_stemmed_str = ' '.join(sent.stemmed)
                if sent_stemmed_str in used_sents: continue
                used_sents.add(sent_stemmed_str)

                ## remove sentences with no query overlap
                #if sent.sim_basic(self.problem.query) <= 0: continue

                ## get units
                units = self.unit_selector(sent.stemmed)

                ## concepts that appear in this sentence
                curr_concepts = set([u for u in units if u in concept_weights])

                ## skip sentences with no concepts
                if len(curr_concepts) == 0: continue

                ## add sentence and its concepts
                relevant_sents.append(sent)
                sent_concepts.append(curr_concepts)
                used_concepts.update(curr_concepts)

            ## create an index for mapping concepts to integers
            concept_weights_final = {}
            concept_index = {}
            index = 0
            for concept in used_concepts:
                concept_index[concept] = index
                concept_weights_final[concept] = concept_weights[concept]
                index += 1
            concept_weights = concept_weights_final

            ## set member variables
            self.concept_weight_sets.append(concept_weights)
            self.concept_index_sets.append(concept_index)
            self.relevant_sent_sets.append(relevant_sents)
            self.relevant_sent_concepts.append([[concept_index[c] for c in cs] for cs in sent_concepts])

        return True



def concept_compare(mapper, gold_mapper):
    """
    compare mapper's concepts to the gold concepts
    """
    ## get concepts for the gold mapper (mapper should already be done)
    gold_mapper.map_concepts()
    gold_mapper.choose_sents()
    gold_mapper.format_output()

    for update_index in [0]:
        print('update [%d]' %update_index)

        gold_sorted_keys = prob_util.Counter(gold_mapper.concept_weight_sets[update_index]).sortedKeys()
        for concept in gold_sorted_keys:
            gold_weight = gold_mapper.concept_weight_sets[update_index][concept]
            try: heuristic_weight = mapper.concept_weight_sets[update_index][concept]
            except: heuristic_weight = 0
            print('my[%1.2f] gold[%1.2f]  [%s]' %(heuristic_weight, gold_weight, ' '.join(concept), ))

        heur_sorted_keys = prob_util.Counter(mapper.concept_weight_sets[update_index]).sortedKeys()
        for concept in heur_sorted_keys:
            if concept in gold_sorted_keys: continue
            heuristic_weight = mapper.concept_weight_sets[update_index][concept]
            print('my[%1.2f] gold[%1.2f]  [%s]' %(heuristic_weight, 0, ' '.join(concept)))
        print('----------------------------')

