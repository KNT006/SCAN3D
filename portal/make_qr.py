"""Create and decode-check a QR containing only the public landing URL."""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools/python-libs'))
import qrcode
import zxingcpp
from PIL import Image, ImageDraw, ImageFont


def generate(url, output):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('QR must contain an HTTPS website URL without secrets')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=12,border=4)
    qr.add_data(url);qr.make(fit=True)
    image=qr.make_image(fill_color='black',back_color='white').convert('RGB')
    path=output/'SCAN3D_网站二维码.png';image.save(path)
    decoded=zxingcpp.read_barcode(image)
    if not decoded or decoded.text!=url:raise RuntimeError('QR round-trip validation failed')
    canvas=Image.new('RGB',(1080,1320),'#f2f8f7')
    draw=ImageDraw.Draw(canvas)
    fonts=Path('C:/Windows/Fonts')
    fontfile=fonts/'msyh.ttc'
    def font(size):return ImageFont.truetype(str(fontfile),size)
    draw.rounded_rectangle((60,50,1020,1270),radius=28,fill='#fffefa',outline='#cad7d2',width=2)
    draw.text((540,115),'SCAN3D',font=font(66),fill='#1c5d5f',anchor='mm')
    draw.text((540,195),'私人陈列馆',font=font(38),fill='#283338',anchor='mm')
    # Integer QR scaling preserves sharp module boundaries.
    modules=qr.modules_count+qr.border*2
    side=modules*max(1,760//modules)
    shown=image.resize((side,side),Image.Resampling.NEAREST)
    canvas.paste(shown,((1080-shown.width)//2,265))
    y=265+shown.height+55
    draw.text((540,y),'我的藏品 · 上传与交付',font=font(29),fill='#1c5d5f',anchor='mm')
    host=parsed.hostname
    host_font=font(18)
    draw.text((540,y+55),host,font=host_font,fill='#647b77',anchor='mm')
    draw.text((540,1175),'公网试用入口 · 电脑及隧道需保持运行',font=font(23),fill='#647b77',anchor='mm')
    draw.text((540,1215),'隧道重建后请使用新二维码',font=font(23),fill='#647b77',anchor='mm')
    poster=output/'SCAN3D_扫码入口海报.png';canvas.save(poster)
    check=zxingcpp.read_barcode(canvas)
    if not check or check.text!=url:raise RuntimeError('Poster QR validation failed')
    (output/'公网地址.txt').write_text(url+'\n',encoding='utf-8')
    (output/'二维码校验.json').write_text(json.dumps({'url':url,'qr_decoded':decoded.text,'poster_decoded':check.text,'status':'pass'},ensure_ascii=False,indent=2),encoding='utf-8')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('url');parser.add_argument('--output',default=str(ROOT/'data/public-delivery'))
    args=parser.parse_args();print(generate(args.url,args.output))
