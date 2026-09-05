import os
import re
import json
import datetime
from pathlib import Path
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock

# ------------------- 核心解析函数 -------------------
def parse_express_info_from_text(full_text):
    lines = [line.strip() for line in full_text.strip().split('\n') if line.strip()]
    results = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if '取件码' in line:
            station = lines[i-1] if i-1>=0 and '取件码' not in lines[i-1] else ''
            cabinet = ''
            code = ''
            if '|' in line:
                left, right = line.split('|',1)
                left, right = left.strip(), right.strip()
                if '号柜' in left or '柜' in left:
                    cabinet = left
                match = re.search(r'取件码\s*([^\s]+)', right)
                if match:
                    code = match.group(1)
            else:
                match = re.search(r'取件码\s*([^\s]+)', line)
                if match:
                    code = match.group(1)
            if i+1 < len(lines):
                next_line = lines[i+1]
                company, address = '', ''
                if '|' in next_line:
                    parts = next_line.split('|',1)
                    company = parts[0].strip()
                    address = parts[1].strip() if len(parts)>1 else ''
                else:
                    company = next_line
            else:
                company, address = '', ''
            if code:
                results.append({
                    '驿站名': station,
                    '快递公司': company,
                    '地址': address,
                    '取件码': code,
                    '柜号': cabinet,
                    '运单号': '',
                    '收件人': '',
                    '手机尾号': '',
                    '存放费': '',
                    '来源文件': ''
                })
            i += 1
            continue
        if '取件' in line or '凭' in line:
            code_match = re.search(r'凭\s*([A-Za-z0-9\-]+)', line) or \
                         re.search(r'取件码\s*([^\s]+)', line) or \
                         re.search(r'(\d{6,10})', line)
            code = code_match.group(1) if code_match else ''
            if not code:
                i += 1
                continue
            cabinet_match = re.search(r'([A-E]?\d*?)柜', line)
            cabinet = cabinet_match.group(0) if cabinet_match else ''
            address = ''
            if '至' in line:
                addr_part = line.split('至',1)[1]
                for stop in ['取件','柜','，','。','.']:
                    if stop in addr_part:
                        address = addr_part.split(stop,1)[0].strip()
                        break
                else:
                    address = addr_part.strip()
            fee_match = re.search(r'超时收([\d.]+)元', line)
            fee = fee_match.group(0) if fee_match else ''
            company = ''
            for name in ['中通','圆通','韵达','申通','顺丰','邮政','兔喜']:
                if name in line:
                    company = name
                    break
            results.append({
                '驿站名': '',
                '快递公司': company,
                '地址': address,
                '取件码': code,
                '柜号': cabinet,
                '运单号': '',
                '收件人': '',
                '手机尾号': '',
                '存放费': fee,
                '来源文件': ''
            })
            i += 1
            continue
        i += 1
    return results

def process_folder(folder_path, data_file='取件记录.json'):
    all_records = []
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            try:
                all_records = json.load(f)
            except:
                all_records = []
    for file in Path(folder_path).iterdir():
        if not file.is_file():
            continue
        ext = file.suffix.lower()
        text_content = ''
        if ext in ('.txt',):
            with open(file, 'r', encoding='utf-8') as f:
                text_content = f.read()
        elif ext in ('.jpg','.jpeg','.png','.bmp'):
            # 移动端暂不支持 OCR，跳过图片
            continue
        else:
            continue
        if text_content.strip():
            records = parse_express_info_from_text(text_content)
            for rec in records:
                rec['来源文件'] = file.name
            all_records.extend(records)
    unique = []
    seen = set()
    for rec in all_records:
        key = (rec['取件码'], rec['地址'], rec['柜号'])
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    return unique

# ------------------- Kivy 界面 -------------------
class ExpressApp(App):
    def build(self):
        self.title = '快递取件管理器'
        self.data_file = '取件记录.json'
        self.root = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        self.folder_input = TextInput(text='/sdcard/取件资料', multiline=False)
        self.select_btn = Button(text='选择文件夹', size_hint_y=0.1)
        self.select_btn.bind(on_press=self.select_folder)
        
        self.process_btn = Button(text='处理并提取', size_hint_y=0.1)
        self.process_btn.bind(on_press=self.process)
        self.clean_btn = Button(text='清理旧文件（3天前）', size_hint_y=0.1)
        self.clean_btn.bind(on_press=self.cleanup)
        
        self.scroll = ScrollView()
        self.result_grid = GridLayout(cols=1, size_hint_y=None)
        self.result_grid.bind(minimum_height=self.result_grid.setter('height'))
        self.scroll.add_widget(self.result_grid)
        
        self.root.add_widget(self.folder_input)
        self.root.add_widget(self.select_btn)
        self.root.add_widget(self.process_btn)
        self.root.add_widget(self.clean_btn)
        self.root.add_widget(self.scroll)
        
        Clock.schedule_once(self.load_data, 0.5)
        return self.root

    def select_folder(self, instance):
        popup = Popup(title='选择文件夹', content=FileChooserListView(path='/sdcard'), size_hint=(0.9, 0.9))
        popup.content.bind(on_submit=self.on_folder_selected)
        popup.open()

    def on_folder_selected(self, chooser, selection, *args):
        if selection:
            self.folder_input.text = selection[0]

    def process(self, instance):
        folder = self.folder_input.text.strip()
        if not os.path.isdir(folder):
            self.show_popup('错误', '文件夹不存在，请重新选择')
            return
        deleted = self.cleanup_old_files(folder)
        new_records = process_folder(folder, self.data_file)
        self.load_data()
        self.show_popup('完成', f'共提取/更新 {len(new_records)} 条记录，清理了 {deleted} 个旧文件')

    def cleanup(self, instance):
        folder = self.folder_input.text.strip()
        if not os.path.isdir(folder):
            self.show_popup('错误', '文件夹不存在')
            return
        deleted = self.cleanup_old_files(folder)
        self.show_popup('清理完成', f'已删除 {deleted} 个超过3天的旧文件')

    def cleanup_old_files(self, folder):
        now = datetime.datetime.now()
        deleted = 0
        for file in Path(folder).iterdir():
            if file.is_file() and file.suffix.lower() in ('.txt', '.jpg', '.jpeg', '.png', '.bmp'):
                mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
                if (now - mtime).days > 3:
                    try:
                        os.remove(file)
                        deleted += 1
                    except:
                        pass
        return deleted

    def load_data(self, *args):
        self.result_grid.clear_widgets()
        if not os.path.exists(self.data_file):
            return
        with open(self.data_file, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except:
                data = []
        for item in data:
            label_text = f"{item.get('快递公司','')} | {item.get('地址','')} | 取件码:{item.get('取件码','')} | 柜号:{item.get('柜号','')}"
            if item.get('存放费'):
                label_text += f" | 费用:{item['存放费']}"
            lbl = Label(text=label_text, size_hint_y=None, height=40, text_size=(self.root.width-20, None), halign='left')
            self.result_grid.add_widget(lbl)

    def show_popup(self, title, content):
        popup = Popup(title=title, content=Label(text=content), size_hint=(0.8, 0.4))
        popup.open()

if __name__ == '__main__':
    ExpressApp().run()
