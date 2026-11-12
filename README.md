# nalmatch

Reconcile a GIS parcel layer against the tax roll and name every parcel that exists on one side
only. Refuses an ID rule that gives two identifiers on one side the same key, and names every
match that exists only because a leading zero was added.

A 312 lot subdivision disappeared from a county's public parcel search for nine months. The roll
extract had come through a spreadsheet, which read the parcel identifier as a number and dropped
its leading zero, so `049300117` arrived as `49300117`. The nightly join matched on the
identifier, found nothing for any of those 312 lots, and finished.

Nobody noticed, because the join succeeded. It matched 900 parcels out of 1212 and reported no
error, and 900 matched rows look exactly like a healthy night. The 312 were missing from the
output rather than wrong in it, and nothing counts what is missing. The call came from a title
company nine months later. The story is illustrative: its figures cannot be
checked from this repository, and the self-test pins only the 312 lot count and the padding
arithmetic.

The quoted run is an excerpt: a line that reads `...` stands for self-test lines left out, and
the first two lines and the last two lines are the real header and footer.

```
$ python nalmatch.py --self-test
nalmatch self-test: no network, no database, a temporary directory for the io layer
--------------------------------------------------------------------
PASS  the default profile is the Florida one, which is what every assertion below is written against
PASS  the default column is the one the Department of Revenue extract uses  <-- pinned defect
PASS  ten records are listed under each class by default  <-- pinned defect
PASS  two profiles ship
PASS  florida-nal folds case, strips punctuation and refuses non-ASCII
PASS  and pads numbers to the widest one it was given
PASS  with a 26 character ceiling
PASS  check digit stripping is OFF by default: it deletes a character from every identifier  <-- pinned defect
PASS  generic folds case, because a lower case identifier is the same identifier
PASS  and does NOTHING else: every rule that can merge two parcels has to be asked for  <-- pinned defect
PASS  profiles() hands back a fresh copy, so one run cannot edit the rule another run gets
PASS  replace() copies rather than editing in place
PASS  a rule reprs as its name
PASS  replacing a rule that does not exist raises rather than being silently ignored  <-- pinned defect
...
PASS  two parcels that differ only by a leading zero make the padding rule REFUSE  <-- pinned defect
PASS  and the verdict is REFUSED
PASS  one key is contested
PASS  named as the key they share
PASS  and BOTH originals are named, because either one could be the parcel the roll meant  <-- pinned defect
PASS  the side is named too
PASS  a collision reprs as its side, its key and its size
PASS  a match count exists internally, and describe() refuses to print it  <-- pinned defect
PASS  the report says REFUSED
PASS  and prints no match count under a merging rule  <-- pinned defect
PASS  nor any of the four classes, which would all be wrong  <-- pinned defect
PASS  it prints both originals instead
PASS  and says what to do about it
PASS  the json carries the refusal
PASS  naming both identifiers in the order the file had them
PASS  under the key this rule gave them both
PASS  and no match count, no class list and no counts at all, so a script that skips the verdict cannot read an empty list as none found  <-- pinned defect
...
PASS  each nine characters wide with a leading zero
PASS  and eight wide after a spreadsheet read them as numbers
PASS  all 312 reconcile once the lost zero is padded back  <-- pinned defect
PASS  and the whole subdivision is unconfirmed, because no match is exact  <-- pinned defect
PASS  and with padding off NOT ONE of them matches, which is the join that succeeded  <-- pinned defect
PASS  every parcel is reported on one side only
...
PASS  and the tool names that pair as matched only by padding, because it cannot tell a lost zero from two parcels  <-- pinned defect
...
PASS  and the offset is the position in the FILE, not in the decoder chunk that held it  <-- pinned defect
...
PASS  and that missing cell is rejected rather than crashing the run
PASS  with the word None printed nowhere  <-- pinned defect
PASS  a blank line between records in a one column file is a record with an empty identifier, not a line the reader drops  <-- pinned defect
PASS  so the run rejects it and does not reconcile, instead of exit 0 over a record it lost  <-- pinned defect
PASS  blank lines at the end of the file are not records
...
PASS  the identifier column guards a leading equals with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading plus with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading minus with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading at sign with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading tab with one apostrophe and changes no other cell  <-- pinned defect
PASS  the identifier column guards a leading carriage return with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading equals with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading plus with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading minus with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading at sign with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading tab with one apostrophe and changes no other cell  <-- pinned defect
PASS  the key column guards a leading carriage return with one apostrophe and changes no other cell  <-- pinned defect
PASS  the detail column guards a leading equals with one apostrophe and changes no other cell  <-- pinned defect
PASS  the detail column guards a leading plus with one apostrophe and changes no other cell  <-- pinned defect
PASS  the detail column guards a leading minus with one apostrophe and changes no other cell  <-- pinned defect
...
PASS  so a spaced identifier is written raw while its trimmed KEY is guarded
PASS  a file of hostile identifiers is reported and written
PASS  every hostile identifier reaches the file with one apostrophe in front  <-- pinned defect
PASS  and so does a KEY that starts with = + or -  <-- pinned defect
PASS  so no IDENTIFIER or KEY cell in the file starts with a trigger  <-- pinned defect
...
PASS  the detail column reaches the FILE with a leading tab guarded and no other cell changed  <-- pinned defect
PASS  the detail column reaches the FILE with a leading carriage return guarded and no other cell changed  <-- pinned defect
...
PASS  end to end: the default run exits 0 and names the one pair that matched only because of padding  <-- pinned defect
...
PASS  and does not fire on a longer module name or a comment
PASS  and that search really was run over this file's own source
PASS  a unique prefix of --apply is refused by the parser, not read as the write flag  <-- pinned defect
PASS  and nothing is written
PASS  an unknown flag exits 64, the usage code the README gives, and not argparse's 2  <-- pinned defect
PASS  so does a flag value of the wrong kind
PASS  and --help still exits 0
PASS  while a run that returns a code instead of exiting reports no SystemExit
PASS  the footer of a green run is the count and 0 failed
PASS  the footer of a red run names every failed assertion and returns 1
--------------------------------------------------------------------
547 assertions, 0 failed
```

## Requirements

Python 3.9 or newer and nothing else. No `arcpy`, no third-party package, no network, no
database. Both sides are CSVs, which is what every parcel layer and every roll extract can be
exported as.

The self-test runs 547 assertions and the count is the same on every interpreter it was run on:
Windows CPython 3.9.25, 3.12.10 and 3.13.2, ArcGIS Pro's own interpreter (3.13.7), and Ubuntu
CPython 3.12.3. There is no unavoidable difference between hosts. Measured with
`coverage run --branch nalmatch.py --self-test` (coverage 7.16.1), branch coverage is 100%
(1261 statements, 204 branches, 0 missed). That figure depends on one `# pragma: no cover` on
the `if __name__ == "__main__"` line. Running the file as a program does execute
`sys.exit(main())`. What cannot be reached is the other arc of that `if`, the one taken when
the file is imported, because the self-test runs the file as the program. Without the pragma,
the same run reports 1263 statements, 206 branches, one partial branch (the `if` line, 2588 to the exit) and 99%. The exit codes
`main()` forwards are asserted through `main()` directly.

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
| Length ceiling | 26 characters | none |
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
7,123456789012345678901234567
```

```
$ python nalmatch.py parcels.csv nal.csv
nalmatch: parcels.csv 7 record(s), nal.csv 5 record(s)

KEY RULE  profile florida-nal, fold case, strip punctuation, pad numbers to 9, ceiling 26 characters, reject non-ASCII
MATCHED   4 key(s) on both sides
PADDED    4 of those matched only because zeros were added, so they may be two parcels that share digits
      gis 049300117  =  roll 49300117  ->  049300117
      gis 049300118  =  roll 49300118  ->  049300118
      gis 049300119  =  roll 49300119  ->  049300119
      gis 049300120  =  roll 49300120  ->  049300120
GIS ONLY  1 parcel(s) with no roll record
      049399999  ->  049399999
ROLL ONLY 1 roll record(s) with no parcel
      13000501  ->  013000501
DUPLICATE 0 key(s) written more than once
REJECTED  2 identifier(s) this profile will not use
      (empty)  ->  empty once trimmed, so there is no identifier to match on
      123456789012345678901234567  ->  longer than this profile allows, so it belongs to a different identifier scheme
VERDICT: DOES NOT RECONCILE
```

The same two files with `--pad off`, which is the join that ran for nine months:

```
$ python nalmatch.py parcels.csv nal.csv --pad off
nalmatch: parcels.csv 7 record(s), nal.csv 5 record(s)

KEY RULE  profile florida-nal, fold case, strip punctuation, no padding, ceiling 26 characters, reject non-ASCII
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
      123456789012345678901234567  ->  longer than this profile allows, so it belongs to a different identifier scheme
VERDICT: DOES NOT RECONCILE
```

Both outputs above are real runs of this file on the two synthetic CSVs. With padding, four
parcels match, the `PADDED` section names each of the four as a match that needed a zero added,
and the two leftovers are named. Without it, nothing matches and the four
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
gives two differently spelled identifiers on one side the same key, the join will succeed and be wrong: one parcel gets the
other's roll record, and nothing anywhere reports an error.

```
$ cat merge.csv          $ cat small.csv
PARCEL_ID                PARCEL_ID
123456                   9
0123456

$ python nalmatch.py merge.csv small.csv
nalmatch: merge.csv 2 record(s), small.csv 1 record(s)

KEY RULE  profile florida-nal, fold case, strip punctuation, pad numbers to 7, ceiling 26 characters, reject non-ASCII
REFUSED   this rule gives 2 distinct identifier(s) 1 shared key(s)
      gis key 0123456 is claimed by:
          123456
          0123456
      nothing is reported against a rule that merges parcels. Change the rule or fix the identifiers.
VERDICT: REFUSED
```

The tool names both originals and stops. It does not print a match count, it does not print the
other three classes (`--json` leaves out `matched` and all four class lists for the same
reason), and `--write-csv --apply` writes nothing, because every one of those numbers
was computed under a rule that merges two parcels into one. A tool that reported them would be
publishing an answer it already knows is wrong.

`--pad off` on the same file reports those two as two ordinary unmatched parcels. The collision
is a property of the rule you asked for, not of the data, and the way out is to change the rule.

A header that names the identifier column twice is refused before any key is made, with exit
2. `csv.DictReader` keeps only the last column of that name, so the other would never be read and
the run could report `RECONCILES` over the wrong column.

Two more things are refused, one identifier at a time rather than for the whole run:

- An identifier longer than the profile's ceiling. The Department of Revenue user's guide says
  `PARCEL_ID` "can contain up to 26 alphanumeric characters", so `florida-nal` refuses anything
  longer than 26 once the separators are gone. A 27 digit identifier belongs to a different
  scheme, and the honest answer is to name it, not to trim it to 26 and match it against
  something. A county whose identifiers run longer than the guide allows passes `--max-len`.
- An identifier holding a character outside ASCII. An en dash is not a hyphen and a full width
  digit `U+FF11` is not a `1`. Unicode normalisation (NFKC) folds the full width digit into an
  ASCII `1`, which is a merge by another name. It leaves the en dash alone, so the en dash is
  refused only because it is not one of the listed separators. `--non-ascii allow` matches both
  verbatim instead.

## The normaliser

The whole product is what happens to an identifier before the join sees it, and the order of the
steps matters:

1. **Trim.** Leading and trailing whitespace is never part of an identifier.
2. **Fold case.** `r12345` on one side and `R12345` on the other are one parcel.
3. **Strip the separators** `- . _ /` and the space. `12345-001-000` on one side and
   `12345001000` on the other are one parcel, and so are `12 345` and `12345`. Both spellings on
   the same side are not read as one parcel written twice: the tool cannot tell a case or
   punctuation variant from two parcels, so it counts that as a collision and refuses (class 4).
4. **Apply the ceiling.** Measured here, after the separators are gone, so `1234-5678-9012-3456-7890-1234-567`
   is refused as 27 digits rather than accepted as 33 characters.
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
extract. The Department's 2025 user's guide names the identifier field
`PARCEL_ID`, which is this tool's default on both sides. The same guide says the Department
publishes the NAL, NAP and SDF files as comma-delimited files with the field names in the header
row, so a file downloaded from the Department needs nothing added. Do not add a second header
line: it would be read as a record. The field numbering differs between guide years.

`PARCEL_ID` is the only field name assumed anywhere. A GIS
parcel layer rarely agrees with any of them, which is why `--gis-id-field` and `--roll-id-field`
exist and why naming a column that is not in the file is a usage error that lists the columns
that are (shown for a layer whose identifier column is `PARCELNO`):

```
$ python nalmatch.py parcels.csv nal.csv
error: parcels.csv has no field 'PARCEL_ID'. Name the right one with --gis-id-field. It has: OBJECTID, PARCELNO, ACRES
```

The identifier format itself is a county decision, not a state one, so no format is hardcoded.
The 26 character ceiling in `florida-nal` is the length the Department of Revenue user's guide
gives for `PARCEL_ID` (see References). It is a guard against mixing two keyspaces, and
`--max-len` changes it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Everything reconciles. |
| 1 | Something did not reconcile: class 1, 2, 3, or a rejected identifier. Also verdict `UNCONFIRMED`: every match needed a zero added, so no match is exact. |
| 2 | A file could not be read (not UTF-8, an unterminated quote, empty, no header, or the identifier column named twice), `--write-csv` could not be written, or both files hold a header and no records (verdict `NOTHING TO COMPARE`, never `RECONCILES`). |
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

What the self-test proves is the bytes in the file, in two steps. A real run through `main()`
writes the CSV, reads it back with Python's `csv` module, and checks the IDENTIFIER column for all
six leads and the KEY column for `=`, `+` and `-`. A trimmed key cannot start with a tab or a
carriage return. SIDE, CLASS and DETAIL are fixed text that `main()` cannot make hostile, so a
second set of assertions calls `write_rows()` with a lead in each of the five columns and reads
the written file back for all six leads. A second matrix calls `csv_rows()` in memory. It does not open the file in a
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
- The no-such-field error prints the header line of the file it names, so do not name a file
  whose first line is sensitive.
- OWASP names a tab prefix inside the quoted field as the mitigation that survives Excel. nalmatch
  uses an apostrophe, as xwddiff does, and neither was tested in a spreadsheet.
- The speed figure above comes from a hand measurement (0.11 s on Windows 3.13), and the
  self-test does not run a pair that size.
- It compares identifiers and nothing else. Two rows that match on the key are reconciled here
  even if every other field disagrees. Acreage, owner and use code are somebody else's check.
- There is no `--fix`. The tool decides what the identifier rule should be and names what falls
  out of it. Changing an identifier in a parcel layer is an edit somebody signs for.
- A rule is applied to both sides or to neither. A check digit that exists on one side only
  cannot be handled by a symmetric rule, and stripping the last character of every identifier on
  both sides is the only thing `--check-digit strip` can honestly do.
- A padded match is reported under `PADDED` and in the `--json` document, and it is not in the
  exception CSV. The tool cannot tell a lost zero from two parcels that share digits, so a layer
  `12345` and a roll `012345` match and are named. When some other match is exact, the verdict
  stays `RECONCILES`. When every match needed a zero, the verdict is `UNCONFIRMED` and the exit
  code is 1, because nothing shows that the two sides share one identifier scheme. Read the
  `PADDED` section before you trust a clean run.
- `--pad auto` takes its width from the data in front of it. Two files that both lost their
  leading zeros pad to the short width and match each other, and the tool cannot tell that from
  two files that never had them. Pass `--pad` an exact width when you know it.
- A duplicate identifier is reported but does not stop the run, so a downstream join can still
  double count. The verdict is `DOES NOT RECONCILE` and the exit code is 1. The exception CSV
  names it.
- The guard covers the six leads listed above. OWASP also lists a line feed and full-width
  forms of `=` and `+`. A cell that starts with one of those is written as it came.
- A lead character that follows a space or a line feed is not guarded in the IDENTIFIER column,
  which keeps the raw text, so `  =2` and a line feed followed by `=cmd` are written as they came.
  The trimmed KEY column is guarded. Whether a spreadsheet runs such a cell was not tested.
- An identifier saved as a float, such as `49300117.0`, loses its dot under the separator rule and
  becomes the key `493001170`, which is the key of a different parcel if that parcel exists on
  the other side.
- `--pad` accepts any width. A very large value, such as `--pad 99999999999`, zero fills every
  all-digit key to that length and can exhaust memory. A value above the largest string length Python
  allows, such as `--pad 99999999999999999999999`, ends in an `OverflowError`. Both tracebacks
  exit 1, which reads as "did not reconcile".
- An identifier that holds a line break inside a quoted CSV field is printed as it is, so it can
  add lines to the text report, including a fake `VERDICT` line above the real one. The real
  verdict is the last line and the exit code.
- `--write-csv` with `--apply` opens the path directly and follows a symbolic link, so a link to
  an input file overwrites that file, as the input file itself does.
- A roll file saved without a header row is read with its first record as the header, so the run
  stops with a usage error that lists that record as the column names.
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
- A NUL byte inside an identifier is read as data on Python 3.12 and 3.13. If the same bytes
  appear on both sides they match each other and the run can exit 0. If only one side has them
  the identifier shows up as a mismatch (exit 1). On Python 3.9 the `csv` module raises
  `line contains NUL` and the run exits 2. The self-test does not pin this difference.
- A blank line between two records is read as a record with an empty identifier and rejected,
  in a file of one column or of several. Blank lines at the end of the file are not records,
  because an editor often leaves one there.
- A row with more cells than the header, usually an unquoted comma in an earlier column, is
  read without a warning and shifts the identifier column for that row. The result is a
  mismatch in the report. It is not a guarantee: a shifted cell that happens to equal another
  real identifier can match.
- `--pad auto` also repairs a one-sided loss: layer `1234` matches roll `001234`. That is the
  repair working as designed, it is listed under `PADDED`, and the limit above covers the case
  where both sides lost zeros.
- The redirected-output encoding behaviour behind the backslash escapes (Windows uses the ANSI
  code page) is taken from Python's documentation for `sys.stdout`. It was not tested under every
  Windows locale.
- Only the 2025 Department of Revenue guide was read. The field numbering differs between guide
  years, and earlier guides were not compared.
- The symbolic link behaviour of `--write-csv` comes from Python's `open()`. The self-test does
  not create a link.
- The CSV reader is strict. An unterminated quote is refused with exit 2, because Python's
  default reader would fold the rest of the file into one cell and drop every record in it. Strict
  mode also refuses a closing quote that is followed by more text before the comma, such as
  `"ab"c`, which a lenient reader would accept.
- A run with one exact match and many padded ones is `RECONCILES` and exits 0. The tool cannot
  tell whether the padded ones are lost zeros, so read `PADDED` or the padded count in `--json`.
- The 26 character ceiling replaced an earlier 18 character default. Set `--max-len 18` to get
  the old rule.
- A header-only file on one side, with records on the other, is reported as findings (exit 1),
  not as a failed export (exit 2). Only two empty sides give `NOTHING TO COMPARE`.
- No Unicode normalisation is done under `--non-ascii allow`, so visually identical identifiers
  can be reported as two parcels.
- A write failure ends the run with exit 2 after the report is printed. Check the exit code
  before you read the report as the whole result.
- The report goes to standard output with `print`, so a closed output pipe can end the run with
  a traceback and exit 1.
- The 100% branch figure excludes the `if __name__ == "__main__"` line and the `sys.exit(main())`
  line under it, with a `# pragma: no cover`. The self-test runs the file as the program, so the
  import arm of that `if` cannot be taken.
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
  NAP), 2025: the published files carry field names in the header row (Intended Users), and
  Field 2, `PARCEL_ID`, "can contain up to 26 alphanumeric characters".
  https://floridarevenue.com/property/dataportal/Documents/PTO%20Data%20Portal/User%20Guides/2025%20Users%20guide%20and%20quick%20reference/2025_NAL_SDF_NAP_Users_Guide.pdf
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
