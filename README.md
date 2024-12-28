# Exam Shtocker

Pseudocode of functionality:

```
1. Ask for EASE credentials and API token for File Collection
2. Log in to exampapers.ed.ac.uk, list all exams beginning with INFR (in the page)
  2a. For each exam, download it temporarily
  2b. Calculate the hash of the downloaded exam paper
  2b. On File Collection, find the category corresponding to the INFR code
  2c. Download every exam within that category, and check if any of them have a matching hash
  2d. If no hash matches, mark that exam as upload-able
3. Give the user the option to select any or all of the missing exams to upload
4. Upload the selected PDF exams to the corresponding category on File Collection
```

Ideally, for each exam paper on exampapers.ed.ac.uk, we want a quick way to check
if the file exists on File Collection. Two ways of doing this is via a date
check (e.g. if exam is for May 2013, check if May 2013 exists in the category),
and a file hash check (check if the file is already in S3). The first option is
not easily doable because there is no date metadata associated with exam papers
unless we extract text from its contents (unreliable). The second option is
equally hard because File Collection randomises exam filenames upon upload, and
doesn't give us a way to quickly check the hash of exams.

We resort to essentially a brute-force method of downloading every exam on
File Collection (in the matching category by INFR code) and comparing the file
hash against the one on exampapers.

In order to optimise the solution in terms of local storage requirements, we
try not to store every downloaded file locally, but rather calculate the file
hashes in a streaming manner and store only the file hash in memory.
