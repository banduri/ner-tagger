from setuptools import find_packages, setup
setup(
        name="ner_tagger",
        version="0.1",
        description="an API for ner-tagging",
        author="Alexander Kasper",
        author_email='asklepios@riseup.net',
        platforms=["any"],  # or more specific, e.g. "win32", "cygwin", "osx"
        license="GPLv2+",
        url="",
        packages=find_packages(),
        data_files=[
            ('models',['models/ner-english-ontonotes-large.bin']),
            ('.',['download_and_convert_model_for_local_use.py','nerapi.py','ner-clean-cache.sh','modelServer.py','cacheServer.py','zmqBroker.py']),
            ('nltk_data/tokenizers/punkt/PY3',['nltk_data/tokenizers/punkt/PY3/german.pickle','nltk_data/tokenizers/punkt/PY3/english.pickle']),
            ('nltk_data/tokenizers/punkt',['nltk_data/tokenizers/punkt/english.pickle','nltk_data/tokenizers/punkt/german.pickle'])
        ],
        include_package_data=True
        )
