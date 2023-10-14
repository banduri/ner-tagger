from flair.nn import Classifier

# download model from huggingface and save it as a local on
# see https://huggingface.co/flair for alternatives
# remember to use a different cache-file if a different model is used

ner_tagger = Classifier.load('ner-ontonotes-large')
ner_tagger.save("models/ner-english-ontonotes-large.bin")

