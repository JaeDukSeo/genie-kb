import pickle
from array import array
from threading import Lock
import numpy as np

class KB:
    """
     KB represents a knowledge base of contexts with "points of interest", i.e., parts of the context
     that ought to be predicted.
     """
    def __init__(self):
        # holds all contexts
        self.__contexts = dict()
        # holds all spans of interest for aligned contexts
        self.__starts = dict()
        self.__ends = dict()
        # hold answers to respective spans, if None answer, span in context is answer itself
        self.__answers = dict()
        # holds all offsets for spans and contexts which are all stored in one memory efficient array
        self.__context_offsets = dict()
        self.__span_offsets = dict()
        # holds list of all symbols
        self.__vocab = list()
        self.__answer_vocab = list()
        # holds list of symbol frequencies
        self.__count = list()
        self.__answer_count = list()
        # holds mappings of symbols to indices in every dimension
        self.__ids = dict()
        self.__answer_ids = dict()
        # additional information
        self.__max_context_length = 0
        self.__max_span_length = 0
        # is ordered
        self.__ordered = False
        #lock for multi-threaded add
        self.__lock = Lock()

    def add(self, context, spans, answers=None, dataset="train"):
        self.__lock.acquire()
        self.__ordered = False
        try:
            assert len(spans) > 0, 'each context should at least have one point of interest.'
            if dataset not in self.__contexts:
                self.__contexts[dataset] = array('I')
                self.__starts[dataset] = array('I')
                self.__ends[dataset] = array('I')
                self.__answers[dataset] = array('I')
                self.__context_offsets[dataset] = list()
                self.__span_offsets[dataset] = list()

            self.__context_offsets[dataset].append(len(self.__contexts[dataset]))
            self.__span_offsets[dataset].append(len(self.__starts[dataset]))
            self.__contexts[dataset].extend(self.__add_to_vocab(w) for w in context)
            for span in spans:
                self.__starts[dataset].append(span[0])
                self.__ends[dataset].append(span[1])
            if answers is not None and self.__answers:
                assert len(answers) == len(spans), "answers must tail -f align with spans"
                for answer in answers:
                    self.__answers[dataset].append(self.__add_to_answer_vocab(answer))
                    # add answers also to normal vocabulary
                    self.__add_to_vocab(answer)
            self.__max_context_length = max(self.__max_context_length, len(context))
            self.__max_span_length = max(self.__max_span_length, len(spans))
        finally:
            self.__lock.release()
        return self.num_contexts(dataset)-1

    def __add_to_vocab(self, key):
        if key not in self.__ids:
            self.__ids[key] = len(self.__vocab)
            self.__vocab.append(key)
            self.__count.append(0)

        i = self.__ids[key]
        self.__count[i] += 1
        return i

    def __add_to_answer_vocab(self, key):
        if key not in self.__answer_ids:
            self.__answer_ids[key] = len(self.__answer_vocab)
            self.__answer_vocab.append(key)
            self.__answer_count.append(0)

        i = self.__answer_ids[key]
        self.__answer_count[i] += 1
        return i

    def save(self, file):
        with open(file, 'wb') as f:
            pickle.dump(self.values(), f)

    def load(self, file):
        with open(file, 'rb') as f:
            self.load_values(pickle.load(f))

    def load_values(self, values):
        [self.__contexts, self.__starts, self.__ends, self.__answers,
         self.__vocab, self.__ids, self.__answer_vocab, self.__answer_ids,
         self.__count, self.__answer_count,
         self.__context_offsets, self.__span_offsets, self.__ordered,
         self.__max_context_length, self.__max_span_length] = values

    def values(self):
        return [self.__contexts, self.__starts, self.__ends, self.__answers,
                self.__vocab, self.__ids, self.__answer_vocab, self.__answer_ids,
                self.__count, self.__answer_count,
                self.__context_offsets, self.__span_offsets, self.__ordered,
                self.__max_context_length, self.__max_span_length]

    def context(self, i, dataset="train"):
        offset = self.__context_offsets[dataset][i]
        end = self.__context_offsets[dataset][i + 1] if i + 1 < len(self.__context_offsets[dataset]) else len(self.__contexts[dataset])
        return self.__contexts[dataset][offset:end]

    def num_contexts(self, dataset):
        return len(self.__context_offsets.get(dataset, []))

    def spans(self, i, dataset="train"):
        offset = self.__span_offsets[dataset][i]
        end = self.__span_offsets[dataset][i + 1] if i + 1 < len(self.__span_offsets[dataset]) else len(self.__starts[dataset])
        return self.__starts[dataset][offset:end], self.__ends[dataset][offset:end]

    def answers(self, i, dataset="train"):
        offset = self.__span_offsets[dataset][i]
        end = self.__span_offsets[dataset][i + 1] if i + 1 < len(self.__span_offsets[dataset]) else len(self.__answers[dataset])
        if self.__answers:
            return self.__answers[dataset][offset:end]
        else:
            # if now answers provided used starts as answers
            return [self.context(dataset, i)[p] for p in self.__starts[dataset][offset * 2:end * 2]]

    def answer_id_to_word_id(self, answer_id):
        w = self.answer_vocab[answer_id]
        return self.id(w)

    def iter_contexts(self, dataset="train"):
        for i in range(len(self.__context_offsets[dataset])):
            yield self.context(dataset, i)

    def iter_spans(self, dataset="train"):
        for i in range(len(self.__span_offsets[dataset])):
            yield self.spans(dataset, i)

    def iter_answers(self, dataset="train"):
        for i in range(len(self.__span_offsets[dataset])):
            yield self.answers(dataset, i)

    @property
    def max_context_length(self):
        return self.__max_context_length

    @property
    def max_span_length(self):
        return self.__max_span_length

    def id(self, word, fallback=-1):
        return self.__ids.get(word, fallback)

    @property
    def vocab(self):
        return self.__vocab

    def answer_id(self, answer, fallback=-1):
        return self.__answer_ids.get(answer, fallback)

    @property
    def answer_vocab(self):
        return self.__answer_vocab

    def order_vocab_by_freq(self):
        if not self.__ordered:
            sorted = np.argsort(self.__count)[::-1]
            mapping = [0 for _ in range(len(self.__vocab))]
            new_vocab = []
            new_counts = []
            for i, k in enumerate(sorted):
                mapping[k] = i
                new_vocab.append(self.__vocab[k])
                new_counts.append(self.__count[k])

            self.__vocab = new_vocab
            self.__count = new_counts

            for w, i in self.__ids.items():
                self.__ids[w] = mapping[i]

            for _, ctxt in self.__contexts.items():
                for i in range(len(ctxt)):
                    ctxt[i] = mapping[ctxt[i]]

            self.__ordered = True


class FactKB:

    def __init__(self, kb=None):
        self.__kb = KB() if kb is None else kb
        self.__entity_vocab = []
        self.__entity_ids = dict()
        self.__entity_ctxt = dict()
        self.__entity_ctxt_span = dict()
        self.__facts = dict()
        self.__lock = Lock()

    def add(self, fact, entity_spans, entities=None, dataset="train"):
        self.__lock.acquire()
        try:
            if not isinstance(fact, list):
                fact = fact.split()
            assert entities is None or len(entities) == len(entity_spans), "Need to provide entity names for all spans."
            entities = ['_'.join(fact[span[0]:span[1]]) for span in entity_spans] if entities is None else entities
            fact_id = self.__kb.add(fact, entity_spans, entities, dataset)

            if dataset not in self.__facts:
                self.__facts[dataset] = []
                self.__entity_ctxt[dataset] = [[] for _ in self.__entity_ids]
                self.__entity_ctxt_span[dataset] = [[] for _ in self.__entity_ids]

            for e, (start, end) in zip(entities, entity_spans):
                if e not in self.__entity_ids:
                    self.__entity_ids[e] = len(self.__entity_vocab)
                    self.__entity_vocab.append(e)
                    for ds in self.__entity_ctxt:
                        self.__entity_ctxt[ds].append([])
                        self.__entity_ctxt_span[ds].append([])
                id = self.__entity_ids[e]
                self.__entity_ctxt[dataset][id].append(fact_id)
                self.__entity_ctxt_span[dataset][id].append((start, end))
                self.__facts[dataset].append(fact_id)
        finally:
            self.__lock.release()
        return fact_id

    def save(self, file):
        with open(file, 'wb') as f:
            pickle.dump(self.values(), f)

    def load(self, file):
        with open(file, 'rb') as f:
            self.load_values(pickle.load(f))

    def load_values(self, values):
        [self.__entity_vocab, self.__entity_ids, self.__entity_ctxt, self.__entity_ctxt_span, self.__facts] = values[:5]
        self.__kb.load_values(values[5:])

    def values(self):
        return [self.__entity_vocab, self.__entity_ids, self.__entity_ctxt, self.__entity_ctxt_span, self.__facts] + self.__kb.values()

    def facts_about(self, entity, dataset):
        id = entity
        if isinstance(id, str):
            id = self.__entity_ids.get(entity)
        if id is None:
            return []
        else:
            return self.__entity_ctxt[dataset][id]

    def fact_from_id(self, fact_id, dataset):
        return self.__kb.context(fact_id, dataset)

    def fact_entities(self, fact_id, dataset):
        return self.__entity_ctxt[dataset][fact_id], self.__entity_ctxt_span[dataset][fact_id]

    @property
    def kb(self):
        return self.__kb

    def id(self, entity, fallback=-1):
        return self.__entity_ids.get(entity, fallback)

    @property
    def entity_vocab(self):
        return self.__entity_vocab
