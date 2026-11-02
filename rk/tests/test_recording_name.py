"""Names and collisions only; never starts capture."""
import importlib.util
from pathlib import Path
import tempfile,unittest
module=Path(__file__).resolve().parents[1]/'rootfs/opt/scan3d-recorder/recording_name.py'
spec=importlib.util.spec_from_file_location('recording_name',module);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Names(unittest.TestCase):
 def test_unicode_and_extension(self):self.assertEqual(m.stem(' 娃娃 展示.mkv '),'娃娃 展示')
 def test_invalid(self):
  for name in ('../foo','a/b','a\\b','.hidden','\n','a\x00b','a:b','😀'*46):
   with self.subTest(name=name),self.assertRaises(ValueError):m.stem(name)
 def test_collision(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'娃娃.mkv').write_bytes(b'original');(p/'.logs').mkdir();(p/'.logs/娃娃-2.log').touch()
   self.assertEqual(m.available(p,'娃娃'),'娃娃-3');self.assertEqual((p/'娃娃.mkv').read_bytes(),b'original')
if __name__=='__main__':unittest.main()
