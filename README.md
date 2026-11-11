# nalmatch

Reconcile a GIS parcel layer against the tax roll and name every parcel that exists on one side
only. Refuses any ID rule that would merge two parcels into one key.

A 312 lot subdivision disappeared from a county's public parcel search for nine months. The roll
extract had come through a spreadsheet, which read the parcel identifier as a number and dropped
its leading zero, so `049300117` arrived as `49300117`. The nightly join matched on the
identifier, found nothing for any of those 312 lots, and finished.

Nobody noticed, because the join succeeded. It matched 900 parcels out of 1212 and reported no
error, and 900 matched rows look exactly like a healthy night. The 312 were missing from the
output rather than wrong in it, and nothing counts what is missing. The call came from a title
company nine months later.

```
$ python nalmatch.py --self-test
nalmatch self-test: no network, no database, a temporary directory for the io layer
--------------------------------------------------------------------
PASS  ten records are listed under each class by default  <-- pinned defect
PASS  check digit stripping is OFF by default: it deletes a character from every identifier  <-- pinned defect
PASS  and does NOTHING else: every rule that can merge two parcels has to be asked for  <-- pinned defect
PASS  the roll identifier that lost its leading zeros in a spreadsheet still matches  <-- pinned defect
PASS  punctuation and lost leading zeros together, which is the join in the story  <-- pinned defect
PASS  an identifier one digit short does not match: padding makes it 01234500100, not the original  <-- pinned defect
PASS  two numbers of the same width are never brought together by padding  <-- pinned defect
PASS  nor a 19 digit identifier from another county's scheme, which is rejected rather than truncated  <-- pinned defect
PASS  and the same 19 digit identifier on BOTH sides still does not match, because neither side made a key  <-- pinned defect
PASS  letter O typed for digit zero does not match, and is not guessed at  <-- pinned defect
PASS  an en dash is not a hyphen: the profile refuses it as non-ASCII rather than treating it as a separator  <-- pinned defect
PASS  full width digits are refused, not folded into ASCII ones  <-- pinned defect
PASS  a number already wider than the width is left alone, never cut  <-- pinned defect
PASS  a key with a letter in it is NOT padded: a lettered identifier is not a number with zeros missing  <-- pinned defect
PASS  an explicit width wider than the profile ceiling still pads to it: the ceiling measures the identifier that arrived, and padding is the repair applied after it  <-- pinned defect
PASS  an entry that carries a key AND a refusal reason sets no width: pad_width trusts the reason, not the key  <-- pinned defect
PASS  the ceiling is checked BEFORE the check digit is stripped, so a foreign identifier cannot be trimmed into profile  <-- pinned defect
PASS  a superscript two is not a number here either  <-- pinned defect
PASS  an identifier that arrived as an int is refused: the leading zeros are already gone and padding would invent them  <-- pinned defect
PASS  a NaN is refused as a number rather than compared, because NaN is not equal to itself and would match nothing  <-- pinned defect
PASS  a one million character cell is refused by the ceiling rather than padded, sliced or crashed on  <-- pinned defect
PASS  a trailing non-breaking space is trimmed like any other whitespace, so it never reaches the ASCII test  <-- pinned defect
PASS  and so is a lone surrogate, rather than raising on the encode  <-- pinned defect
PASS  two parcels that differ only by a leading zero make the padding rule REFUSE  <-- pinned defect
PASS  and BOTH originals are named, because either one could be the parcel the roll meant  <-- pinned defect
PASS  a match count exists internally, and describe() refuses to print it  <-- pinned defect
PASS  nor any of the four classes, which would all be wrong  <-- pinned defect
PASS  with padding off the same two parcels keep different keys and nothing is refused  <-- pinned defect
PASS  case folding merges two rows whose identifiers really did differ, and that is still a refusal  <-- pinned defect
PASS  a collision on the ROLL side is refused too: the merge is just as wrong in that direction  <-- pinned defect
PASS  the same identifier written twice is a duplicate, not a merge, so the run is not refused  <-- pinned defect
PASS  a missing cell shows as empty, never as the word None  <-- pinned defect
PASS  and the word None appears nowhere in the report  <-- pinned defect
PASS  all 312 reconcile once the lost zero is padded back  <-- pinned defect
PASS  and with padding off NOT ONE of them matches, which is the join that succeeded  <-- pinned defect
PASS  a rejected 19 digit identifier does not set the padding width for the rest of the file  <-- pinned defect
PASS  a rejected identifier is not ALSO reported as unmatched: it is one finding, not two  <-- pinned defect
...
PASS  check() and raises() really do record a failure  <-- pinned defect
PASS  a byte order mark does not become part of the first field name  <-- pinned defect
PASS  with the word None printed nowhere  <-- pinned defect
PASS  three parcels reconcile through the padding rule, read off disk  <-- pinned defect
PASS  and NOTHING matches, which is the join in the story  <-- pinned defect
PASS  without it the default column is missing and that is a usage error, not an empty report  <-- pinned defect
PASS  --write-csv alone writes NOTHING  <-- pinned defect
PASS  and says how many rows went into it, which is the only count the operator sees about the write  <-- pinned defect
PASS  --apply over an existing file replaces it: the authorisation is the flag  <-- pinned defect
PASS  and not one stale row survives the rewrite  <-- pinned defect
PASS  and writes NOTHING, because the rule that made those rows merges parcels  <-- pinned defect
PASS  and when BOTH spellings are in the layer, stripping the check digit merges two records and the run is refused  <-- pinned defect
...
PASS  the identifier column guards a leading equals with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading tab with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading carriage return with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading equals with one apostrophe and changes no other cell  <-- pinned defect
PASS  the detail column guards a leading equals with one apostrophe and changes no other cell  <-- pinned defect
PASS  a number or None passes through unchanged, so a numeric column stays numeric  <-- pinned defect
PASS  every hostile identifier reaches the file with one apostrophe in front  <-- pinned defect
PASS  dropping that one apostrophe gives the input identifier back for every identifier that did not start with an apostrophe, which is the round trip a reader of the file would apply
PASS  an identifier with a hyphen inside it is written exactly as read, with no apostrophe
PASS  but the run refuses an identifier column named twice: exit 2, not RECONCILES over the column csv kept  <-- pinned defect
...
PASS  and every rule override defaults to 'whatever the profile says'  <-- pinned defect
PASS  nalmatch imports no network module: there is no upload path to audit, and no credential for one to carry
PASS  a unique prefix of --apply is refused by the parser, not read as the write flag  <-- pinned defect
PASS  the footer of a green run is the count and 0 failed
PASS  the footer of a red run names every failed assertion and returns 1
--------------------------------------------------------------------
488 assertions, 0 failed

```

## Requirements

Python 3.9 or newer and nothing else. No `arcpy`, no third-party package, no network, no
database. Both sides are CSVs, which is what every parcel layer and every roll extract can be
exported as.

The self-test runs 488 assertions and the count is the same on every interpreter it was run on:
Windows CPython 3.9.25, 3.12.10 and 3.13.2, ArcGIS Pro's own interpreter (3.13.7), and Ubuntu
CPython 3.12.3. There is no unavoidable difference between hosts. Measured with
`coverage run --branch nalmatch.py --self-test` (coverage 7.16.1), branch coverage is 100%
(1147 statements, 176 branches, 0 missed). The one line the self-test cannot reach is
`sys.exit(main())` under `if __name__ == "__main__"`, which runs only when the file is the
program and is marked `# pragma: no cover`. The exit codes it forwards are asserted through
`main()` directly.

```
git clone https://github.com/uhsear/nalmatch.git
```

## Quick start

```
python nalmatch.py --self-test
python nalmatch.py parcels.csv nal.csv
```

## Usage

Export the parcel layer to CSV, point the tool at it and at the roll extract, and name the
identifier column on each side if it is not `PARCEL_ID`.

```
python nalmatch.py parcels.csv nal.csv
python nalmatch.py parcels.csv nal.csv --gis-id-field PARCELNO
python nalmatch.py parcels.csv nal.csv --profile generic --punctuation strip
python nalmatch.py parcels.csv nal.csv --write-csv exceptions.csv --apply
python nalmatch.py parcels.csv nal.csv --json > nalmatch.json
```

| Flag | Default | What it does |
|---|---|---|
| `GIS` | none | The parcel layer as a CSV. Required unless `--self-test`. |
| `ROLL` | none | The roll extract as a CSV. Required unless `--self-test`. |
| `--profile` | `florida-nal` | Identifier rule to start from: `florida-nal` or `generic`. |
| `--gis-id-field` | `PARCEL_ID` | Identifier column in the parcel layer. |
| `--roll-id-field` | `PARCEL_ID` | Identifier column in the roll extract. |
| `--case` | profile | `fold` to upper case, or `keep` the case as it arrived. |
| `--punctuation` | profile | `strip` the separators `- . _ /` and the space, or `keep` them. |
| `--pad` | profile | `auto`, an exact width, or `off`. Leading zeros, restored. |
| `--check-digit` | profile | `strip` the last character of every identifier, or `keep` it. |
| `--max-len` | profile | Refuse an identifier longer than N characters. `0` is no ceiling. |
| `--non-ascii` | profile | `reject` an identifier outside ASCII, or `allow` it verbatim. |
| `--sample` | `10` | How many records to list under each class. `0` lists none. |
| `--write-csv` | off | Write the exception rows to this CSV. Needs `--apply`. |
| `--apply` | off | Actually write. Without it nothing is written. |
| `--json` | off | Write the report as JSON on stdout instead of text. |
| `--self-test` | off | Run the assertions and exit. Takes no other flag. |

The two profiles:

| Rule | `florida-nal` | `generic` |
|---|---|---|
| Fold case | yes | yes |
| Strip `- . _ /` and the space | yes | no |
| Pad numbers with leading zeros | yes, to the widest seen | no |
| Strip a trailing check digit | no | no |
| Length ceiling | 18 characters | none |
| Non-ASCII identifier | rejected | matched verbatim |

`generic` does the least a rule can do: trim the whitespace and fold the case. Every rule that
can bring two different identifiers together has to be asked for by name.

## What one run says

Two small synthetic files stand in for the story. The layer holds the parcels as the county
numbers them. The roll came through a spreadsheet and lost the leading zero.

```
parcels.csv                          nal.csv
OBJECTID,PARCEL_ID                   PARCEL_ID,OWNER
1,049300117                          49300117,A
2,049300118                          49300118,B
3,049300119                          49300119,C
4,049300120                          49300120,D
5,049399999                          13000501,E
6,
7,1234567890123456789
```

```
$ python nalmatch.py parcels.csv nal.csv
nalmatch: parcels.csv 7 record(s), nal.csv 5 record(s)

KEY RULE  profile florida-nal, fold case, strip punctuation, pad numbers to 9, ceiling 18 characters, reject non-ASCII
MATCHED   4 key(s) on both sides
GIS ONLY  1 parcel(s) with no roll record
      049399999  ->  049399999
ROLL ONLY 1 roll record(s) with no parcel
      13000501  ->  013000501
DUPLICATE 0 key(s) written more than once
REJECTED  2 identifier(s) this profile will not use
      (empty)  ->  empty once trimmed, so there is no identifier to match on
      1234567890123456789  ->  longer than this profile allows, so it belongs to a different identifier scheme
VERDICT: DOES NOT RECONCILE
```

The same two files with `--pad off`, which is the join that ran for nine months:

```
$ python nalmatch.py parcels.csv nal.csv --pad off
nalmatch: parcels.csv 7 record(s), nal.csv 5 record(s)

KEY RULE  profile florida-nal, fold case, strip punctuation, no padding, ceiling 18 characters, reject non-ASCII
MATCHED   0 key(s) on both sides
GIS ONLY  5 parcel(s) with no roll record
      049300117  ->  049300117
      049300118  ->  049300118
      049300119  ->  049300119
      049300120  ->  049300120
      049399999  ->  049399999
ROLL ONLY 5 roll record(s) with no parcel
      49300117  ->  49300117
      49300118  ->  49300118
      49300119  ->  49300119
      49300120  ->  49300120
      13000501  ->  13000501
DUPLICATE 0 key(s) written more than once
REJECTED  2 identifier(s) this profile will not use
      (empty)  ->  empty once trimmed, so there is no identifier to match on
      1234567890123456789  ->  longer than this profile allows, so it belongs to a different identifier scheme
VERDICT: DOES NOT RECONCILE
```

Both outputs above are real runs of this file on the two synthetic CSVs. With padding, four
parcels match and the two leftovers are named. Without it, nothing matches and the four
parcels that lost a zero sit in both lists.

## Why not just join the two tables

Because the join already works. The Add Join tool in ArcGIS Pro matches "when the input field
and join field values are equal", a pandas `merge` matches on the key you give it, and a `LEFT
JOIN` in the database does the same. A pandas merge with `indicator=True` goes further and tells
you which side each row came from (`left_only`, `right_only`, `both`), which is classes 1 and 2
above for one keyword. If you only need to know what did not match under a key you already
trust, use it.

None of the three has an opinion about the key. They match the identifier you hand them, and they
report a clean join over whatever subset agreed. The 312 lots in the story were not a join bug:
the join did exactly what it was told. The gap is the identifier rule in front of it, and a rule
that quietly merges two parcels is the one failure a join can never report, because a merged join
succeeds.

That is the whole of this tool. It decides the rule, names what falls out of it, and refuses to
report anything at all under a rule that gives two distinct parcels the same key.

## What it checks (or refuses)

Four classes do not reconcile, and one of them stops the run.

**1. Parcels with no roll record.** A parcel exists in the layer and the roll has never heard of
it. Either the roll is missing it, or the identifier is spelled differently on the two sides.

**2. Roll records with no parcel.** The other direction. A parcel the county is taxing and the
map does not draw.

**3. Duplicate identifiers.** The same identifier written twice on one side. The join returns
that parcel twice and every count downstream is one too many. This is reported, not refused: a
repeated row is a data entry problem, not a key problem.

**4. Identifiers that collide only after normalisation.** This is the one the tool exists for,
and it is the only one that stops the run. If stripping punctuation or padding leading zeros
gives two distinct parcels the same key, the join will succeed and be wrong: one parcel gets the
other's roll record, and nothing anywhere reports an error.

```
$ cat merge.csv          $ cat small.csv
PARCEL_ID                PARCEL_ID
123456                   9
0123456

$ python nalmatch.py merge.csv small.csv
nalmatch: merge.csv 2 record(s), small.csv 1 record(s)

KEY RULE  profile florida-nal, fold case, strip punctuation, pad numbers to 7, ceiling 18 characters, reject non-ASCII
REFUSED   this rule gives 2 distinct identifier(s) 1 shared key(s)
      gis key 0123456 is claimed by:
          123456
          0123456
      nothing is reported against a rule that merges parcels. Change the rule or fix the identifiers.
VERDICT: REFUSED
```

The tool names both originals and stops. It does not print a match count, it does not print the
other three classes, and `--write-csv --apply` writes nothing, because every one of those numbers
was computed under a rule that merges two parcels into one. A tool that reported them would be
publishing an answer it already knows is wrong.

`--pad off` on the same file reports those two as two ordinary unmatched parcels. The collision
is a property of the rule you asked for, not of the data, and the way out is to change the rule.

A header that names the identifier column twice is refused before any key is made, with exit
2. `csv.DictReader` keeps only the last column of that name, so the other would never be read and
the run could report `RECONCILES` over the wrong column.

Two more things are refused, one identifier at a time rather than for the whole run:

- An identifier longer than the profile's ceiling. A 19 digit identifier in a Florida county's
  file belongs to a different scheme, and the honest answer is to name it, not to trim it to 18
  and match it against something.
- An identifier holding a character outside ASCII. An en dash is not a hyphen and a full width
  digit `U+FF11` is not a `1`. Unicode normalisation would fold both into the ASCII key, which is
  a merge by another name. `--non-ascii allow` matches them verbatim instead.

## The normaliser

The whole product is what happens to an identifier before the join sees it, and the order of the
steps matters:

1. **Trim.** Leading and trailing whitespace is never part of an identifier.
2. **Fold case.** `r12345` and `R12345` are one parcel.
3. **Strip the separators** `- . _ /` and the space. `12345-001-000` and `12345001000` are one
   parcel, and so are `12 345` and `12345`.
4. **Apply the ceiling.** Measured here, after the separators are gone, so `1234-5678-9012-3456-789`
   is refused as 19 digits rather than accepted as 23 characters.
5. **Strip a check digit,** if asked. After the ceiling, so an identifier from another scheme can
   never be trimmed into profile.
6. **Pad with leading zeros.** Last, so an identifier the profile refused can never set the width
   the rest of the file is padded to.

Padding is the step that repairs the disaster, and it is also the one most likely to merge two
parcels. The width is the widest all-digit identifier the tool accepted on either side, so
`49300117` from the spreadsheet becomes `049300117` again and matches the layer. Only all-digit
keys are padded: `A42` is not a number that lost its zeros. A key already wider than the width is
left alone, never cut.

`str.isdigit()` is not the test used. It answers `True` for a full width digit and for a
superscript two, and both would then be padded with ASCII zeros into a key nobody typed. An
identifier is an ASCII number here or it is not a number.

An identifier that arrives as a Python `int` rather than as text is refused outright. `csv` gives
text for every cell, so a number reaching this code came through a reader that already parsed it,
which is the exact moment the leading zeros were lost. Padding a guess back on would be inventing
an identifier.

## Field names

The Florida tax roll is the Department of Revenue NAL (name, address, legal) and NAP extract,
one file for each county. The Department's 2025 user's guide names the identifier field
`PARCEL_ID`, which is this tool's default on both sides. The Department's 2025 submission
standard says those files are comma-delimited with no header row, so add a header line (for
example `CO_NO,PARCEL_ID,...`, in the order the user's guide gives for your year) before you
point nalmatch at one. The field numbering differs between guide years.

`PARCEL_ID` is the only field name assumed anywhere. A GIS
parcel layer rarely agrees with any of them, which is why `--gis-id-field` and `--roll-id-field`
exist and why naming a column that is not in the file is a usage error that lists the columns
that are:

```
$ python nalmatch.py parcels.csv nal.csv
error: parcels.csv has no field 'PARCEL_ID'. Name the right one with --gis-id-field. It has: OBJECTID, PARCELNO, ACRES
```

The identifier format itself is a county decision, not a state one, so no format is hardcoded.
The 18 character ceiling in `florida-nal` is a guard against mixing two keyspaces rather than a
statement about any statute, and `--max-len` changes it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Everything reconciles. |
| 1 | Something did not reconcile: class 1, 2, 3, or a rejected identifier. |
| 2 | A file could not be read (not UTF-8, empty, no header, or the identifier column named twice), `--write-csv` could not be written, or both files hold a header and no records (verdict `NOTHING TO COMPARE`, never `RECONCILES`). |
| 3 | Refused. The identifier rule would merge two parcels. |
| 64 | Usage error. |

Exit 3 is deliberately not exit 1. A script that treats "some parcels did not match" as routine
must not treat "this key rule is wrong" the same way.

## The exception CSV and spreadsheets

`--write-csv` copies identifiers from the two input files into a CSV that somebody opens in a
spreadsheet. A text cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return can be
read there as a formula, and an identifier is free text. OWASP calls this CSV injection and lists
those leading characters (see References). nalmatch puts one apostrophe in front of every such
text cell, in all five columns, as the last step before the row is written.

- The rule is the same in every column: only text, only a cell that starts with one of the six
  characters, and exactly one apostrophe. `12-3` is written as it came. `-8` becomes `'-8`.
- A number or an empty value is not text, so it is not touched. Today every column is text, so
  this is a property of the function and not of any column.
- Drop the one leading apostrophe and you get the identifier back, with one exception: an
  identifier that already starts with an apostrophe is written as it came, because an
  apostrophe is not a lead. `=7` and `'=7` therefore both reach the file as `'=7`, and the file
  cannot tell them apart. The self-test pins the round trip for the six leads and pins this
  ambiguity.
- nalmatch never reads its own CSV. `read_csv_rows` reads only the two files you name, so there
  is no strip on read. Do not feed the exception file back in as an input.
- The apostrophe is visible text in the cell. It is a guard, not a display format.

What the self-test proves is the bytes in the file: it writes the CSV, reads it back with Python's
`csv` module, and checks every guarded column for every lead. It does not open the file in a
spreadsheet, so what Excel or another program does with the apostrophe is OWASP's claim here and
not something this repository tested. OWASP also warns that a quote prefix can fail in Excel
after the file is saved and opened again.

## Remapped identifiers and filtered rows

nalmatch has no crosswalk. It does not map a legacy identifier to the identifier that replaced it.
A legacy identifier can carry an ASCII character outside the separators, such as `12345#001`. That
character stays in the key, so `12345#001` does not match `12345001`. Both appear in the report:
one under GIS ONLY and one under ROLL ONLY. The tool names the pair, but it does not say that
they are one parcel. If the county renumbered parcels, apply your own crosswalk first. Then run
nalmatch on the translated column.

nalmatch also sees only the rows in the two CSVs. If a selection rule filtered either side before
the export, the rows it dropped never reach the tool, and no class reports them. A rules-based
selection drops rows without a trace, just as a join does. Make the step that filters write
out what it left out, grouped by reason.

## Limits

- CSV only. No geodatabase, no shapefile, no SDE connection, no fixed width reader. Export both
  sides. A CSV is the one format every roll extract and every parcel layer can produce, and
  reading a geodatabase would need `arcpy`, which would stop the tool running anywhere else.
- It reads both files into memory. A 1215 row pair runs in well under a second; a statewide file
  is not what this is for.
- It compares identifiers and nothing else. Two rows that match on the key are reconciled here
  even if every other field disagrees. Acreage, owner and use code are somebody else's check.
- There is no `--fix`. The tool decides what the identifier rule should be and names what falls
  out of it. Changing an identifier in a parcel layer is an edit somebody signs for.
- A rule is applied to both sides or to neither. A check digit that exists on one side only
  cannot be handled by a symmetric rule, and stripping the last character of every identifier on
  both sides is the only thing `--check-digit strip` can honestly do.
- `--pad auto` takes its width from the data in front of it. Two files that both lost their
  leading zeros pad to the short width and match each other, and the tool cannot tell that from
  two files that never had them. Pass `--pad` an exact width when you know it.
- A duplicate identifier is reported but does not stop the run, so a downstream join can still
  double count. The exception CSV names it.
- The guard covers the six leads listed above. OWASP also lists a line feed and full-width
  forms of `=` and `+`. A cell that starts with one of those is written as it came.
- A lead character that follows a space is not guarded in the IDENTIFIER column, which keeps
  the raw text. The trimmed KEY column is guarded. Whether a spreadsheet runs such a cell was
  not tested.
- Both files must be UTF-8. Anything else is refused with exit 2 and a message naming the byte
  and its offset, rather than decoded with replacement characters.
- Case folding covers ASCII letters only, so under `--non-ascii allow` an accented letter and
  its capital stay two identifiers.
- Do not point `--write-csv` at one of your input files: with `--apply` it replaces that input.
- A refused run (exit 3) with `--apply` leaves any existing file at the `--write-csv` path
  untouched, so a stale exception CSV from an earlier run stays on disk.
- The exception file is opened for writing directly, so a failure part way through (a full
  disk) can leave a truncated CSV together with exit 2.
- The exception CSV is UTF-8 without a byte order mark. A spreadsheet may show an identifier
  that passed `--non-ascii allow` as garbled text. This was not tested in a spreadsheet.
- Identifiers the console cannot encode are shown as backslash escapes in the report. The CSV
  is always UTF-8. The report otherwise prints identifiers as they are, so an identifier that
  holds terminal control characters is echoed to the terminal.
- A cell longer than the `csv` module's 131072 character limit makes the whole file exit 2
  with a message. The one million character check in the self-test is about the identifier rule only.
- A NUL byte inside an identifier is read as data on Python 3.13 and then matches
  nothing clean, so it shows up as a mismatch and not as a read error.
- A line that is completely empty is dropped by the `csv` module, so in a one-column file an
  empty identifier written as a blank line is neither counted nor reported. Rows with several
  columns are counted and reported.
- A row with more cells than the header, usually an unquoted comma in an earlier column, is
  read without a warning and shifts the identifier column for that row. The result is a
  mismatch in the report, not a false match.
- `--pad auto` also repairs a one-sided loss: layer `1234` matches roll `001234`. That is the
  repair working as designed, and the limit above covers the case where both sides lost zeros.
- Nothing is written without `--apply`, and a refused run writes nothing at all.
- It opens no socket and imports no network module, so there is no credential anywhere in it to
  leak. The self-test checks the import statements in its own source for the common network
  modules. It does not see `__import__` or `importlib`, so it is a tripwire for an ordinary
  edit and not a proof.

## References

- OWASP, "CSV Injection": the leading characters (`=`, `+`, `-`, `@`, tab, carriage return, line
  feed) and the single quote prefix as one mitigation, with the warning that it can fail in
  Excel after a save and reopen. https://owasp.org/www-community/attacks/CSV_Injection
- Esri, "Add Join (Data Management)": a match is made when the input field and join field values
  are equal; unmatched input records are kept or dropped by the join type.
  https://doc.esri.com/en/arcgis-pro/latest/tool-reference/data-management/add-join.html
- pandas, `pandas.merge`: `indicator=True` adds a `_merge` column holding `left_only`,
  `right_only` or `both`. https://pandas.pydata.org/docs/reference/api/pandas.merge.html
- Python documentation, `str.isdigit`: digits include the compatibility superscript digits, and
  a full width digit is a decimal character, so both pass `isdigit()`.
  https://docs.python.org/3/library/stdtypes.html#str.isdigit
- Florida Department of Revenue, "User's Guide, Department Property Tax Data Files" (NAL, SDF,
  NAP) and the annual submission standard, which says the roll files carry no header row.
  https://floridarevenue.com/property/dataportal/Documents/PTO%20Data%20Portal/User%20Guides/2025%20Users%20guide%20and%20quick%20reference/2025_NAL_SDF_NAP_Users_Guide.pdf
  and https://floridarevenue.com/property/Documents/2025FINALCompSubmStd.pdf
- Python documentation, `csv`: `csv.writer` writes `None` as the empty string and stringifies
  every other non-string value, and a file passed to it should be opened with `newline=''`.
  https://docs.python.org/3/library/csv.html

## Contributing

Open an issue or pull request on GitHub.

## Author

Built by [Asir Khan](https://www.linkedin.com/in/asir-khan-310317264/).

## License

MIT.

## Related

Other single-file tools in this portfolio that pair with this one:

- [fcload](https://github.com/uhsear/fcload) - load the reconciled result without corrupting it
- [roadmiles](https://github.com/uhsear/roadmiles) - the same refusal to certify a number nobody checked
- [geocodesift](https://github.com/uhsear/geocodesift) - the same lesson applied to a geocoded batch
- [pl94](https://github.com/uhsear/pl94) - census blocks for the same county, reconciled against the county total
