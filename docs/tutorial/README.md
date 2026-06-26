# Tutorial

Before you start, keep these common actions in mind:

> 1. Press the left/right arrow keys to switch to the previous / next paper.
>
> 2. Press the number keys `1` `2` `3` `4` to quickly color-tag a paper.
>
> 3. On small-screen devices, swipe left/right to switch to the previous / next paper.
>
> 4. The page has a built-in share button to quickly share a paper worth keeping.
>
> 5. Save a paper you like to Zotero with one click and auto-generate a summary note.

## Entry points

Most of this project's entry points are collected in the small gear at the bottom-left: admin management, retrieval configuration, workflow triggering, and more.

<p align="center">
  <img src="docs/tutorial/tutorial-entry-panel.png" alt="Entry panel" width="50%" />
</p>

After opening the admin panel, click "Add" to create a new topic entry.

First enter the direction you actually want to track in "Retrieval requirement", then click "Generate candidates", and select the topics you want to keep from the candidate results.

<p align="center">
  <img src="docs/tutorial/tutorial-topic-setup.png" alt="Topic creation and candidate generation" width="88%" />
</p>

We recommend keeping keywords to **8 or fewer** and natural-language queries to **5 or fewer**, which makes it easier to maintain recall quality and a manageable configuration.

After saving the query, remember to save the entry once more. Once done, click the search-papers area on the right to start your first paper retrieval.

<p align="center">
  <img src="docs/tutorial/tutorial-first-search.png" alt="First paper search" width="50%" />
</p>

---

### Reset content button

The "Delete all" button restores the current repository to the "no papers fetched yet" state, but it **does not reset the password** and does not affect how you unlock.

### Zotero integration

1. Install Zotero

2. Install the [Zotero Connector](https://www.zotero.org/download/connectors)

3. Install `Actions & Tags`  
   [Releases · windingwind/zotero-actions-tags](https://github.com/windingwind/zotero-actions-tags/releases/)

4. Open Zotero settings and complete the configuration under `Actions & Tags`

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-settings.png" alt="Zotero Actions and Tags settings" width="88%" />
</p>

5. Download the script from the repository and import it into Zotero  
   Script link:
   <a href="others/actions-zotero.yml" data-no-router download="actions-zotero.yml">Download actions-zotero.yml</a>

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-script-download.png" alt="Download the Zotero script" width="88%" />
</p>

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-script-import.png" alt="Import the Zotero script" width="88%" />
</p>

After importing and enabling the script, open a paper page; once the Zotero icon state has changed, you can start one-click saving.

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-save-entry.png" alt="One-click save to Zotero from the web" width="88%" />
</p>

After a successful save, you can see the auto-generated summary note in Zotero:

<p align="center">
  <img src="docs/tutorial/tutorial-zotero-note-preview.png" alt="Preview of the Zotero auto-generated summary note" width="88%" />
</p>
