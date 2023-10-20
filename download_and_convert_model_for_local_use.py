import flair
import torch
from flair.nn import Classifier
import spacy

# dont' load the model to gpu 
device = torch.device('cpu')
flair.device = device

# download model from huggingface and save it as a local on
# see https://huggingface.co/flair for alternatives
# remember to use a different cache-file if a different model is used

ner_tagger = Classifier.load('ner-ontonotes-large')
ner_tagger.save("models/ner-english-ontonotes-large.bin")

del ner_tagger

ner_tagger_tpu = Classifier.load('hmteams/flair-hipe-2022-ajmc-de')
ner_tagger_tpu.save("models/flair-hipe-2022-ajmc-de.bin")

del ner_tagger_tpu

ner_tagger_tpu = Classifier.load("hmteams/flair-hipe-2022-newseye-de")
ner_tagger_tpu.save("models/flair-hipe-2022-newseye-de.bin")

del ner_tagger_tpu

send_tagger_de = Classifier.load('de-offensive-language')
send_tagger_de.save("models/de-offensive-language.bin")

del send_tagger_de

send_tagger = Classifier.load('sentiment')
send_tagger.save("models/sentiment.bin")

del send_tagger
nlp = spacy.load("de_dep_news_trf")
nlp.to_disk("./models/de_dep_news_trf.bin")
