import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner/scan3d'))
from scan_names import rename_scan,validate_title,title_for,export_stem,named_report

class ScanNamesTest(unittest.TestCase):
 def test_rename_preserves_identity_and_payload(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'scan3d-test';p.mkdir()
   original=dict(title='旧摆件',object_name='旧摆件',count=137,status='complete')
   (p/'status.json').write_text(json.dumps(original),encoding='utf-8')
   (p/'points.npz').write_bytes(b'unchanged')
   result=rename_scan(p,' 新摆件 ')
   self.assertEqual(result,dict(id=p.name,title='新摆件'))
   self.assertEqual(title_for(p),'新摆件')
   self.assertEqual((p/'points.npz').read_bytes(),b'unchanged')
   self.assertEqual(json.loads((p/'status.json').read_text())['original_title'],'旧摆件')
   rename_scan(p,'再次命名')
   self.assertEqual(json.loads((p/'status.json').read_text())['original_title'],'旧摆件')
   report=named_report(p,original)
   self.assertEqual(report['title'],'再次命名');self.assertEqual(report['object_name'],'再次命名')
   self.assertEqual(original['title'],'旧摆件');self.assertEqual(report['count'],137)
 def test_invalid_names_do_not_change_archive(self):
  for value in ('','   ','a'*81,'x\ny','x\x00y',None,42):
   with self.subTest(value=value),self.assertRaises(ValueError):validate_title(value)
 def test_export_filename_cannot_escape_directory(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)
   (p/'status.json').write_text(json.dumps({'title':'../猫\\:/模型'}))
   self.assertNotIn('/',export_stem(p));self.assertNotIn('\\',export_stem(p))
   self.assertNotIn(':',export_stem(p))

if __name__=='__main__':unittest.main()
