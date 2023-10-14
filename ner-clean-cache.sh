#!/bin/bash
#

systemctl stop taz-ner-tagger

# keep the last 3mill cache entries
#

tail -n 3000000 /opt/venvs/taz-ner-tagger/data/cache_data.ndjson > /opt/venvs/taz-ner-tagger/data/cache_data.new

rm /opt/venvs/taz-ner-tagger/data/cache_data.ndjson

mv /opt/venvs/taz-ner-tagger/data/cache_data.new /opt/venvs/taz-ner-tagger/data/cache_data.ndjson

systemctl start taz-ner-tagger

