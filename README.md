# Ibis Bot Collection

This repository contains bot implementations using the ibots package

## Dependencies

`$ pip install -e <local ibots package>`

`$ pip install -r requirements.txt`

`$ python -m spacy download en`

Eventually ibots will be a more stable pypi package by the same name

## Run

1. Obtain login information from your Token Ibis network admin
2. Copy `config.template.json` to something else (e.g. `config.json`)
3. Modify as needed, filling in usernames and passwords

`python -m ibots <config file> <endpoint>`

Example:

`python -m ibots config.json api.dev.tokenibis.org`
