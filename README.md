<h1 align="center">
  Exam Shtocker
</h1>

<p align="center">
  <i align="center">Automatically upload exams onto Better Informatics from ExamPapers.ed.ac.uk 🚀</i>
</p>

![Demo](./demo.gif)

## Introduction

(This tool is intended to be used by Better Informatics administrators.)

`Exam-Shtocker` is a Python (3.12+) command-line tool to search through
Informatics past papers on exampapers.ed.ac.uk using provided EASE credentials,
and upload them to [Better Informatics File Collection](https://files.betterinformatics.com)
under the corresponding category. This alleviates the painful semesterly process
of manually mass-uploading PDFs after each exam diet.

The script intelligently prevents duplicate uploads by comparing file hashes of
each exam PDF against those already uploaded on Better Informatics. It also
uses pyPDF to parse the exam diet string from within the PDF, reducing the BI
maintainer's labor when cutting exams up.

The script is named `Exam-Shtocker` as a play on words containing:
- 'stock' as in "stock up" on exams
- German-like pronunciation of 'stock' -> 'shtock' respecting BI's ETHZ origins
- 取得 (shu-toku) in Japanese meaning "grab/get"

## Features
- Automatic exam-upload, de-duplication, and intelligent file naming
- Interactive CLI tool with pretty colours & progress indicators
- Session caching so credentials only need to be entered infrequently
- Automatic version checker
- In-depth logging available for errors
- Prevents abuse flagging and rate-limiting through random sleeps

## Usage

To run this script, you will need to be a Better Informatics administrator (as
you will need the API key) and have valid EASE credentials.

This project uses Poetry as the Python package management tool. You can likely
also use standalone pip if you install the required packages in `pyproject.toml`,
but this is not directly supported. We used Python 3.12 to develop this
repository. Anything newer should work, but older versions are untested.

Clone this repository, and run:

```
$ poetry install
$ export BI_API_KEY=the_betterinformatics_api_key
$ poetry run python exam_shtocker
```

The script will prompt for EASE credentials as necessary, and save it for future.

Logs will be appended to a file called `exam_shtocker.log`. Run the script with
`-v` for more detailed logs including network request traces.

## Behind the Scenes

To develop `exam-shtocker` locally (to contribute new features or bugfixes), it
may be useful to understand the central logic of `exam-shtocker`. The following
is the pseudocode of the script's functionality.

```
1. Ask for EASE credentials and API token for BI File Collection
2. Log in to exampapers.ed.ac.uk
3. Use the DSpace API (the system that exampapers use) to request a page (100)
   of exams in the School of Informatics, with a PDF copy available. For each
   exam:
  a. Download the exam PDF temporarily
  b. Calculate the file hash of the downloaded exam paper
  c. Check if it's in a known-bad-list
  d. On BI, find the category corresponding to the EUCLID code. Ignore or error
     if the code isn't tracked on BI
  d. Download every exam PDF on BI within that category
  e. Calculate the hash for each exam PDF on BI in that category
  f. If no hash matches:
    一. Parse the exam diet from the first page of the PDF
    二. Upload the exam to File Collection, titled with the parsed exam diet
  g. If the hash exists already:
    一. Skip the file as it is already on BI
```

Our reasoning for this logic is as follows:

Ideally, for each exam paper on exampapers.ed.ac.uk, we want a quick way to check
if the file exists on File Collection. Two ways of doing this is via a date
check (e.g. if exam is for May 2013, check if May 2013 exists in the category),
and a file hash check (check if the file is already in S3).

1. The first option is not easily doable because extracting the exam diet from
   the PDF is unreliable. It also doesn't account for any courses that may have
   different exam contents for UG and PG variants (which may both be titled
   'May 2013').
2. The second option is not very elegant either because File Collection
   randomises exam filenames upon upload (preventing filename existency checks),
   and doesn't provide exam hashes (so we have to calculate it on our own).

We chose method 2 because it seemed slightly more reliable despite being slower.
The script performs the hash check by downloading every exam on File Collection
(in the matching category by EUCLID code) and comparing the file hash against
the one on exampapers. It is very slow and taxing on File Collection's server,
but we think it's acceptable given the script isn't supposed to be run frequently.

Some optimisation is included in the script, such as storing a cache of hashes
per EUCLID code in local memory.
