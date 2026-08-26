# Security and privacy

Please do not report vulnerabilities or private data in a public issue.
Use a GitHub private vulnerability report for this repository when possible.
If that option is unavailable, open a minimal issue asking for a private
contact channel without including the finding or any personal data.

## Data boundary

WSA is local-first. The repository intentionally excludes the local database,
screenshots, reports, logs, virtual environments, and build artifacts through
`.gitignore`. WSA reads only visible WeChat desktop content or user-provided
files; it does not read or modify WeChat's private database, inject into the
WeChat process, or send messages automatically.

Before opening a pull request or publishing a package, verify that no local
`data/`, `reports/`, screenshot, database, log, `.env`, key, or credential file
is staged. Do not paste OCR text, screenshots, contact names, API keys, or
other personal data into issues, pull requests, package metadata, or examples.

## Reporting details

Include the affected version/commit, a minimal reproduction that contains no
personal data, expected and actual behavior, and the impact. Please allow time
for a fix before public disclosure.
