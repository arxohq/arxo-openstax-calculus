from pathlib import Path
import hashlib, json, tempfile, unittest
import boundaries

def _edition(edition_id, work, extent):
    return {"kind":"source_edition","id":edition_id,"work":work,"lifecycle":[{"status":"in_force","extent":extent}]}
def _fragment(frag_id, edition_id, locator):
    return {"kind":"fragment","id":frag_id,"edition":edition_id,"locator":locator}
def _rule(rule_id, anchor):
    return {"kind":"rule","id":rule_id,"anchors":[anchor]}

CNXML_TEXT = '''<document xmlns="http://cnx.rice.edu/cnxml"
 xmlns:md="http://cnx.rice.edu/mdml" xmlns:m="http://www.w3.org/1998/Math/MathML">
 <title>Units</title><metadata><md:content-id>m1</md:content-id>
 <md:title id="metadata-id">Not content</md:title></metadata>
 <content><note id="outer"><para id="p1">One <m:math id="math-id"/>.</para></note>
 <para id="p2">Two</para><!-- <para id="comment-id"/> --></content>
 <glossary><definition id="def"><term id="term">Force</term>
 <meaning id="meaning">A definition.</meaning></definition></glossary></document>'''


def _cnxml_measure(tmp: Path, text: str = CNXML_TEXT,
                   unit: str | None = None, extra: list[dict] | None = None,
                   locator: str = "module/m1#p1") -> dict:
    src = tmp / "m1.cnxml"
    src.write_text(text)
    edition = _edition("edition", "work", {"start": "2000-01-01", "end": "infinity"})
    nodes = [edition, {"kind": "publication", "id": "publication", "edition": "edition",
                      "documentHash": "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()},
             _fragment("f", "edition", locator), _rule("r", "f"),
             _fragment("unused", "edition", "module/m1#p2"), *(extra or [])]
    program = tmp / "own.json"
    program.write_text(json.dumps({"nodes": nodes}))
    return boundaries.depth(src, program, **({"source_unit": unit} if unit else {}))


class CNXMLDepthTests(unittest.TestCase):
    def test_intrinsic_module_and_fine_elements_do_not_roll_up(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module = _cnxml_measure(root)
            self.assertEqual([(r['article'], r['level']) for r in module['rows']],
                             [('m1', 'EXECUTABLE')])
            fine = _cnxml_measure(root, unit='cnxml_element')
            levels = {r['article']: r['level'] for r in fine['rows']}
            self.assertEqual(len(levels), 6)
            self.assertEqual(levels['m1#p1'], 'EXECUTABLE')
            self.assertEqual(levels['m1#p2'], 'SOURCE_ONLY')
            self.assertEqual(levels['m1#outer'], '—')
            self.assertEqual(levels['m1#def'], '—')
            self.assertNotIn('m1#metadata-id', levels)
            self.assertNotIn('m1#math-id', levels)
            self.assertNotIn('m1#comment-id', levels)

    def test_stale_and_wrong_module_fragment_ids_fail(self):
        for locator in ['module/m1#missing', 'module/m2#p1', 'module/m1#p1/paragraph/2']:
            with self.subTest(locator=locator), tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(ValueError, 'does not resolve'):
                    _cnxml_measure(Path(temp), locator=locator)

    def test_ambiguous_or_non_cnxml_sources_fail(self):
        bad = [CNXML_TEXT.replace('id="p2"', 'id="p1"'),
               CNXML_TEXT.replace('<md:content-id>m1</md:content-id>', ''),
               CNXML_TEXT.replace('http://cnx.rice.edu/cnxml', 'urn:other'),
               CNXML_TEXT.replace('<para id="p2">Two</para>', '<para id="bad id">Two</para>')]
        for text in bad:
            with self.subTest(text=text[:30]), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(ValueError):
                    _cnxml_measure(Path(temp), text)

    def test_document_hash_must_match_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _cnxml_measure(root)
            doc = json.loads((root/'own.json').read_text())
            next(n for n in doc['nodes'] if n['kind']=='publication')['documentHash'] = 'sha256:wrong'
            (root/'own.json').write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'source hash is not pinned'):
                boundaries.depth(root/'m1.cnxml', root/'own.json')

    def test_foreign_module_and_nonoverlapping_edition_do_not_count(self):
        extra = [_edition('foreign', 'different-work', {'start':'2000-01-01','end':'infinity'}),
                 _fragment('other-module', 'foreign', 'module/m2#p1'),
                 _rule('other-rule', 'other-module'),
                 _edition('old', 'work', {'start':'1900-01-01','end':'2000-01-01'}),
                 _fragment('old-fragment', 'old', 'module/m1#p2'),
                 _rule('old-rule', 'old-fragment')]
        with tempfile.TemporaryDirectory() as temp:
            result = _cnxml_measure(Path(temp), unit='cnxml_element', extra=extra)
            rows = {r['article']:r for r in result['rows']}
            self.assertEqual(rows['m1#p1']['deriving'],1)
            self.assertEqual(rows['m1#p2']['level'],'SOURCE_ONLY')
            self.assertEqual(result['otherEdition'],2)

    def test_overlapping_edition_cannot_lend_xml_anchors(self):
        extra = [_edition('overlapping', 'work', {'start':'2000-01-01','end':'infinity'}),
                 _fragment('different-text', 'overlapping', 'module/m1#p2'),
                 _rule('different-rule', 'different-text')]
        with tempfile.TemporaryDirectory() as temp:
            result = _cnxml_measure(Path(temp), unit='cnxml_element', extra=extra)
            rows = {r['article']:r for r in result['rows']}
            self.assertEqual(rows['m1#p2']['level'],'SOURCE_ONLY')
            self.assertEqual(result['otherEdition'],1)

    def test_publication_must_resolve_its_edition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _cnxml_measure(root)
            doc = json.loads((root/'own.json').read_text())
            next(n for n in doc['nodes'] if n['kind']=='publication')['edition'] = 'absent'
            (root/'own.json').write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'unresolved edition'):
                boundaries.depth(root/'m1.cnxml',root/'own.json')


    def test_cnxml_locator_is_exact_and_keeps_module_identity(self):
        self.assertEqual(boundaries.locator_units('module/m1#p1','cnxml_module'),('m1',))
        self.assertEqual(boundaries.locator_units('module/m1#p1','cnxml_element'),('m1#p1',))
        self.assertEqual(boundaries.locator_units('module/m2#p1','cnxml_element'),('m2#p1',))
        self.assertEqual(boundaries.locator_units('module/m1#p1','article'),())
        self.assertEqual(boundaries.locator_units('module/m1#p1/extra','cnxml_element'),())
        with self.assertRaises(ValueError):
            boundaries.article_spans(CNXML_TEXT,'cnxml_element')

if __name__ == "__main__": unittest.main()
