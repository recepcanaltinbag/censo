# Publishing CENSO

Two steps, in this order. The second is pointless before the first: a FAIR
assessment marks an ontology unfindable if its IRI does not dereference,
however well built the file is.

## 1. Serve the files somewhere stable

Anything with a permanent HTTPS URL. Two options, both fine:

**GitHub Pages** — conventional for a paper artefact.
Push `ontology/dist/censo-full.{ttl,owl}`, `ontology/reg/*.ttl` and
`ontology/censo-shapes.ttl` to a repository, enable Pages, and the base is
`https://<user>.github.io/<repo>`.

**A university page** — if Boğaziçi provides one with a stable HTTPS URL, that
works too. Avoid any address tied to a department or a personal account that
may be withdrawn: a w3id redirect is permanent, and pointing it at a URL that
later disappears is worse than not registering it.

## 2. Register the w3id redirect

1. Fork <https://github.com/perma-id/w3id.org>
2. Create a directory `censo/`
3. Copy `w3id-censo/.htaccess` into it, replacing every `{{BASE}}` with the
   base URL from step 1
4. Open a pull request. Their guidance asks for a short description and a
   contact address; both are already in the file header.

Once merged, check it:

```bash
curl -sIL -H "Accept: text/turtle" https://w3id.org/censo/ | grep -i location
curl -sIL -H "Accept: application/rdf+xml" https://w3id.org/censo/ | grep -i location
```

## 3. Then run FOOPS!

<https://foops.linkeddata.es/> — paste `https://w3id.org/censo/`, not a file
upload. Uploading a file cannot score Findability or Accessibility, so the
result would understate the ontology and tell you nothing you can act on.
