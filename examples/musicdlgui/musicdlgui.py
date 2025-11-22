'''
Function:
    Implementation of MusicdlGUI
Author:
    Zhenchao Jin
WeChat Official Account (微信公众号):
    Charles的皮卡丘
'''
import os
import sys
import requests
from PyQt5 import *
from PyQt5 import QtCore
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from musicdl import musicdl
from PyQt5.QtWidgets import *
from musicdl.modules.utils.misc import touchdir, sanitize_filepath

# 定义搜索线程类
class SearchThread(QThread):
    # 定义信号
    search_started = pyqtSignal()
    result_ready = pyqtSignal(str, list)
    search_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, music_sources, keyword, timeout=10, source_cookies=None, quality='auto'):
        super(SearchThread, self).__init__()
        self.music_sources = music_sources
        self.keyword = keyword
        self.timeout = timeout
        self.source_cookies = source_cookies or {}  # 格式：{source: {cookie_key: cookie_value}}
        self.quality = quality  # 音质参数
        self.music_client = None
        
    def run(self):
        try:
            self.search_started.emit()
            # 创建music_client并进行搜索
            self.music_client = musicdl.MusicClient(music_sources=self.music_sources)
            
            # 应用每个源的独立cookies
            for source in self.music_sources:
                # 获取该源的cookies
                cookies = self.source_cookies.get(source, {})
                if source in self.music_client.music_clients and cookies:
                    # 为每个客户端设置cookies
                    if hasattr(self.music_client.music_clients[source], 'default_search_cookies'):
                        self.music_client.music_clients[source].default_search_cookies = cookies
                    if hasattr(self.music_client.music_clients[source], 'default_download_cookies'):
                        self.music_client.music_clients[source].default_download_cookies = cookies
                    # 更新请求覆盖参数中的cookies
                    if source in self.music_client.requests_overrides:
                        if 'cookies' not in self.music_client.requests_overrides[source]:
                            self.music_client.requests_overrides[source]['cookies'] = cookies
                        else:
                            self.music_client.requests_overrides[source]['cookies'].update(cookies)
            
            # 使用字典存储已处理的音乐源，避免重复处理
            processed_sources = set()
            
            # 模拟增量搜索结果
            for source in self.music_sources:
                try:
                     # 准备搜索参数，严格按照BaseMusicClient.search方法的参数要求
                     results = self.music_client.music_clients[source].search(
                         keyword=self.keyword,
                         num_threadings=self.music_client.clients_threadings[source],
                         request_overrides=self.music_client.requests_overrides[source],
                         rule=self.music_client.search_rules[source]
                     )
                     
                     # 如果需要音质筛选，可以在这里对结果进行后处理
                     if self.quality != 'auto':
                         # 这里可以根据selected_quality对results进行过滤或排序
                         pass
                     self.result_ready.emit(source, results)
                     processed_sources.add(source)
                except Exception as e:
                    error_msg = f"Error searching {source}: {str(e)}"
                    print(error_msg)
                    self.error_occurred.emit(error_msg)
            
        except Exception as e:
            error_msg = f"Search thread error: {str(e)}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
        finally:
            self.search_finished.emit()
    
    def get_music_client(self):
        return self.music_client


'''MusicdlGUI'''
class MusicdlGUI(QWidget):
    def __init__(self):
        super(MusicdlGUI, self).__init__()
        # initialize
        self.setWindowTitle('MusicdlGUI —— Charles的皮卡丘')
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icon.ico')))
        self.setFixedSize(900, 480)
        self.initialize()
        self.custom_cookies = {}  # 用于存储用户自定义cookies，格式：{source: {cookie_key: cookie_value}}
        self.cookie_status = {}  # 用于存储cookie状态，格式：{source: 'valid'/'invalid'/'unconfigured'}
        # search sources
        self.src_names = ['QQMusicClient', 'KuwoMusicClient', 'MiguMusicClient', 'QianqianMusicClient', 'KugouMusicClient', 'NeteaseMusicClient']
        self.label_src = QLabel('Search Engine:')
        self.check_boxes = []
        for src in self.src_names:
            cb = QCheckBox(src, self)
            cb.setCheckState(QtCore.Qt.Unchecked)  # 默认未勾选
            self.check_boxes.append(cb)
        # input boxes
        self.label_keyword = QLabel('Keywords:')
        self.lineedit_keyword = QLineEdit('尾戒')
        self.button_keyword = QPushButton('Search')
        # search results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(['ID', 'Singers', 'Songname', 'Filesize', 'Duration', 'Album', 'Source'])
        self.results_table.horizontalHeader().setStyleSheet("QHeaderView::section{background:skyblue;color:black;}")
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # mouse click menu
        self.context_menu = QMenu(self)
        self.action_download = self.context_menu.addAction('Download')
        # 音质选择下拉框
        self.label_quality = QLabel('音质选择:')
        self.quality_combobox = QComboBox(self)
        # 定义音质选项
        self.quality_options = [
            ('自动（最高音质）', 'auto'),
            ('MP3 128kbps', 'mp3_128'),
            ('MP3 320kbps', 'mp3_320'),
            ('FLAC无损', 'flac')
        ]
        # 添加音质选项到下拉框
        for name, _ in self.quality_options:
            self.quality_combobox.addItem(name)
        # 默认选择自动（最高音质）
        self.quality_combobox.setCurrentIndex(0)
        
        # progress bar
        self.bar_download = QProgressBar(self)
        self.label_download = QLabel('Download progress:')
        # status label for showing search status
        self.status_label = QLabel('Ready')
        self.status_label.setAlignment(Qt.AlignCenter)
        # Cookie相关按钮
        self.button_import_cookies = QPushButton('配置Cookie')
        self.cookie_menu = QMenu()
        for src in self.src_names:
            action = QAction(f'配置{src}的Cookie', self)
            action.triggered.connect(lambda checked, s=src: self.import_cookies(s))
            self.cookie_menu.addAction(action)
        self.button_import_cookies.setMenu(self.cookie_menu)
        
        # 添加验证所有Cookie按钮
        self.button_validate_all = QPushButton('验证所有Cookie')
        self.button_validate_all.clicked.connect(self.validate_all_cookies)
        
        # 添加清除Cookie按钮（下拉菜单）
        self.button_clear_cookies = QPushButton('清除Cookie')
        self.clear_menu = QMenu()
        # 添加清除所有Cookie选项
        clear_all_action = QAction('清除所有Cookie', self)
        clear_all_action.triggered.connect(self.clear_all_cookies)
        self.clear_menu.addAction(clear_all_action)
        # 添加分隔线
        self.clear_menu.addSeparator()
        # 添加每个源的清除选项
        for src in self.src_names:
            action = QAction(f'清除{src}的Cookie', self)
            action.triggered.connect(lambda checked, s=src: self.clear_cookies(s))
            self.clear_menu.addAction(action)
        self.button_clear_cookies.setMenu(self.clear_menu)
        
        # Cookie状态显示标签
        self.cookie_status_label = QLabel('Cookie状态: 未配置')
        self.cookie_status_label.setAlignment(Qt.AlignLeft)
        
        # grid
        grid = QGridLayout()
        # 第一行：搜索源复选框
        grid.addWidget(self.label_src, 0, 0, 1, 1)
        for idx, cb in enumerate(self.check_boxes): 
            grid.addWidget(cb, 0, idx+1, 1, 1)
        
        # 第二行：关键词输入和搜索按钮
        grid.addWidget(self.label_keyword, 1, 0, 1, 1)
        grid.addWidget(self.lineedit_keyword, 1, 1, 1, len(self.src_names)-3)
        grid.addWidget(self.button_import_cookies, 1, len(self.src_names)-2, 1, 1)
        grid.addWidget(self.button_validate_all, 1, len(self.src_names)-1, 1, 1)
        grid.addWidget(self.button_keyword, 1, len(self.src_names), 1, 1)
        
        # 第三行：Cookie状态显示和清除按钮
        grid.addWidget(self.cookie_status_label, 2, 0, 1, len(self.src_names)-1)
        grid.addWidget(self.button_clear_cookies, 2, len(self.src_names)-1, 1, 2)
        
        # 第四行：下载进度和音质选择
        grid.addWidget(self.label_download, 3, 0, 1, 1)
        grid.addWidget(self.bar_download, 3, 1, 1, len(self.src_names)-3)
        grid.addWidget(self.label_quality, 3, len(self.src_names)-2, 1, 1)
        grid.addWidget(self.quality_combobox, 3, len(self.src_names)-1, 1, 2)
        
        # 第五行：状态标签
        grid.addWidget(self.status_label, 4, 0, 1, len(self.src_names)+1)
        
        # 第六行及以后：搜索结果表格
        grid.addWidget(self.results_table, 5, 0, len(self.src_names), len(self.src_names)+1)
        
        self.grid = grid
        self.setLayout(grid)
        # connect
        self.button_keyword.clicked.connect(self.search)
        self.results_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.mouseclick)
        self.action_download.triggered.connect(self.download)
        # 初始化所有搜索源的复选框样式
        for src in self.src_names:
            self.update_checkbox_style(src)
    '''initialize'''
    def initialize(self):
        # 初始化源名称列表
        self.src_names = ['QQMusicClient', 'KuwoMusicClient', 'MiguMusicClient', 'QianqianMusicClient', 'KugouMusicClient', 'NeteaseMusicClient']
        # 初始化cookie相关字典
        self.cookie_status = {}
        self.custom_cookies = {}
        self.search_results = {}
        self.music_records = {}
        self.selected_music_idx = -10000
        self.music_client = None
        self.search_thread = None
        self.current_row = 0
        # 初始化所有搜索源的cookie状态
        for src in self.src_names:
            if src not in self.cookie_status:
                self.cookie_status[src] = 'unconfigured'
    '''mouseclick'''
    def mouseclick(self):
        self.context_menu.move(QCursor().pos())
        self.context_menu.show()
    '''parse_cookies_string'''
    def parse_cookies_string(self, cookies_str):
        """
        将浏览器控制台复制的Cookie字符串解析为字典格式
        支持两种格式：
        1. key1=value1; key2=value2; ...
        2. key1=value1\nkey2=value2\n...
        """
        cookies = {}
        # 首先尝试用分号分隔（浏览器控制台复制的格式）
        if ';' in cookies_str:
            pairs = cookies_str.split(';')
        else:
            # 否则用换行符分隔
            pairs = cookies_str.split('\n')
        
        for pair in pairs:
            pair = pair.strip()
            if pair and '=' in pair:
                key, value = pair.split('=', 1)
                key = key.strip()
                value = value.strip()
                if key:
                    cookies[key] = value
        return cookies
    
    '''import_cookies'''
    def import_cookies(self, source=None):
        # 如果没有指定源，弹出选择对话框
        if not source:
            source, ok = QInputDialog.getItem(
                self, '选择搜索源', 
                '请选择要为哪个搜索源配置Cookie:',
                self.src_names, 0, False
            )
            if not ok:
                return
        
        # 弹出文本输入对话框让用户粘贴Cookie
        cookies_str, ok = QInputDialog.getMultiLineText(
            self, f'配置{source}的Cookie', 
            '请从浏览器控制台复制Cookie并粘贴到这里:\n(格式: key1=value1; key2=value2; 或每行一个key=value)',
            ''  # 初始为空
        )
        
        if not ok or not cookies_str.strip():
            return
        
        try:
            # 解析Cookie字符串
            cookies = self.parse_cookies_string(cookies_str)
            
            if not cookies:
                raise ValueError('未解析到有效的Cookie')
            
            # 保存cookies到指定源
            self.custom_cookies[source] = cookies
            # 设置状态为未验证
            self.cookie_status[source] = 'unconfigured'
            # 验证cookie有效性
            self.validate_cookie(source)
            
            self.status_label.setText(f'成功为{source}导入Cookie，共{len(cookies)}个键值对')
            QMessageBox.information(self, '成功', f'为{source}导入Cookie成功')
        except Exception as e:
            self.status_label.setText(f'Cookie导入失败: {str(e)}')
            QMessageBox.warning(self, '错误', f'Cookie导入失败: {str(e)}')
    
    '''download'''
    def download(self):
        self.selected_music_idx = str(self.results_table.selectedItems()[0].row())
        song_info = self.music_records.get(self.selected_music_idx)
        
        # 获取用户选择的音质
        quality_index = self.quality_combobox.currentIndex()
        selected_quality = self.quality_options[quality_index][1]
        
        # 准备请求头，包含可能的自定义cookies
        headers = self.music_client.music_clients[song_info['source']].default_download_headers.copy()
        
        # 获取该源的特定cookies
        source = song_info['source']
        source_cookies = self.custom_cookies.get(source, {})
        
        # 根据选择的音质调整下载URL或参数
        download_url = song_info['download_url']
        
        # 使用requests.get，添加该源特定的cookies
        with requests.get(download_url, headers=headers, cookies=source_cookies, stream=True, verify=False) as resp:
            if resp.status_code == 200:
                total_size, chunk_size, download_size = int(resp.headers['content-length']), 1024, 0
                touchdir(song_info['work_dir'])
                download_music_file_path = sanitize_filepath(os.path.join(song_info['work_dir'], song_info['song_name']+'.'+song_info['ext']))
                with open(download_music_file_path, 'wb') as fp:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if not chunk: continue
                        fp.write(chunk)
                        download_size += len(chunk)
                        self.bar_download.setValue(int(download_size / total_size * 100))
        QMessageBox().information(self, 'Successful Downloads', f"Finish downloading {song_info['song_name']} by {song_info['singers']}, see {download_music_file_path}")
        self.bar_download.setValue(0)
    '''search'''
    def search(self):
        # 如果已经有搜索线程在运行，先终止
        if self.search_thread and self.search_thread.isRunning():
            self.search_thread.terminate()
            self.search_thread.wait()
        
        self.initialize()
        # selected music sources
        music_sources = []
        for cb in self.check_boxes:
            if cb.isChecked():
                music_sources.append(cb.text())
        
        # keyword
        keyword = self.lineedit_keyword.text()
        
        # 获取选择的音质
        quality_index = self.quality_combobox.currentIndex()
        selected_quality = self.quality_options[quality_index][1]  # 获取音质值
        
        # 清空表格
        self.results_table.setRowCount(0)
        self.status_label.setText(f'Searching "{keyword}"...')
        self.button_keyword.setEnabled(False)
        
        # 设置合理的超时时间
        timeout = 15  # 15秒
        
        # 创建并启动搜索线程，传入每个源的独立cookies和音质参数
        self.search_thread = SearchThread(music_sources, keyword, timeout, self.custom_cookies, quality=selected_quality)
        self.search_thread.search_started.connect(self.on_search_started)
        self.search_thread.result_ready.connect(self.on_result_ready)
        self.search_thread.search_finished.connect(self.on_search_finished)
        self.search_thread.error_occurred.connect(self.on_search_error)
        self.search_thread.start()
    
    def on_search_started(self):
        self.status_label.setText(f'Searching "{self.lineedit_keyword.text()}"...')
    
    def on_result_ready(self, source, results):
        # 将搜索结果添加到表格中
        self.search_results[source] = results
        
        # 更新表格
        current_rows = self.results_table.rowCount()
        self.results_table.setRowCount(current_rows + len(results))
        
        for result in results:
            # 添加行数据
            row_items = [
                str(self.current_row), 
                result['singers'], 
                result['song_name'], 
                result['file_size'], 
                result['duration'], 
                result['album'], 
                result['source']
            ]
            
            for col, item_text in enumerate(row_items):
                item = QTableWidgetItem(item_text)
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                self.results_table.setItem(self.current_row, col, item)
            
            # 保存记录
            self.music_records[str(self.current_row)] = result
            self.current_row += 1
        
        # 更新状态
        self.status_label.setText(f'Searching... Found {self.current_row} results so far')
        
        # 确保music_client已设置
        if self.search_thread and not self.music_client:
            self.music_client = self.search_thread.get_music_client()
    
    def on_search_finished(self):
        # 搜索完成，更新状态
        total_results = self.results_table.rowCount()
        if total_results == 0:
            self.status_label.setText('Search completed, but no results found.')
        else:
            self.status_label.setText(f'Search completed. Found {total_results} results.')
        self.button_keyword.setEnabled(True)
        
        # 确保music_client已设置
        if self.search_thread:
            self.music_client = self.search_thread.get_music_client()
    
    def on_search_error(self, error_msg):
        # 显示错误消息
        self.status_label.setText(f'Search error: {error_msg}')
        QMessageBox.warning(self, 'Search Error', error_msg)
    
    '''update_checkbox_style'''
    def update_checkbox_style(self, source):
        # 根据cookie状态更新复选框样式
        for i, src in enumerate(self.src_names):
            if src == source:
                status = self.cookie_status.get(source, 'unconfigured')
                if status == 'valid':
                    # 有效cookie，显示绿色
                    self.check_boxes[i].setStyleSheet('color: green;')
                elif status == 'invalid':
                    # 无效cookie，显示红色
                    self.check_boxes[i].setStyleSheet('color: red;')
                else:
                    # 未配置cookie，显示默认颜色
                    self.check_boxes[i].setStyleSheet('')
                break
        # 更新Cookie状态显示
        self.update_cookie_status_display()
    
    '''validate_cookie'''
    def validate_cookie(self, source):
        # 定义各搜索源的验证URL
        validation_urls = {
            'QQMusicClient': 'https://c.y.qq.com/v8/fcg-bin/fcg_v8_homepage_cp.fcg',
            'KuwoMusicClient': 'http://www.kuwo.cn/api/www/bang/bang/musicList',
            'MiguMusicClient': 'https://music.migu.cn/v3/music/playlist',
            'QianqianMusicClient': 'http://music.91q.com/v1/restserver/ting',
            'KugouMusicClient': 'https://www.kugou.com/yy/html/search.html',
            'NeteaseMusicClient': 'https://music.163.com/api/toplist'
        }
        
        # 获取该源的cookie
        cookies = self.custom_cookies.get(source, {})
        if not cookies:
            self.cookie_status[source] = 'unconfigured'
            self.update_checkbox_style(source)
            return
        
        # 获取验证URL
        url = validation_urls.get(source)
        if not url:
            # 如果没有特定的验证URL，设置为未配置
            self.cookie_status[source] = 'unconfigured'
            self.update_checkbox_style(source)
            return
        
        try:
            # 发送HEAD请求验证cookie
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            # 设置超时，避免验证过程过长
            resp = requests.head(url, headers=headers, cookies=cookies, timeout=5, verify=False)
            
            # 根据响应状态判断cookie是否有效
            if 200 <= resp.status_code < 400:
                # 如果响应正常，设置为有效
                self.cookie_status[source] = 'valid'
            else:
                # 如果响应异常，设置为无效
                self.cookie_status[source] = 'invalid'
        except Exception as e:
            # 如果发生异常，设置为无效
            print(f'验证{source}的cookie时出错: {str(e)}')
            self.cookie_status[source] = 'invalid'
        finally:
            # 更新复选框样式
            self.update_checkbox_style(source)
    
    '''validate_all_cookies'''
    def validate_all_cookies(self):
        # 验证所有配置了cookie的搜索源
        self.status_label.setText('正在验证所有Cookie...')
        valid_count = 0
        invalid_count = 0
        configured_count = 0
        
        for source in self.src_names:
            if source in self.custom_cookies and self.custom_cookies[source]:
                configured_count += 1
                self.validate_cookie(source)
                if self.cookie_status.get(source) == 'valid':
                    valid_count += 1
                elif self.cookie_status.get(source) == 'invalid':
                    invalid_count += 1
        
        # 更新状态标签
        if configured_count > 0:
            self.status_label.setText(f'Cookie验证完成: 有效{valid_count}, 无效{invalid_count}, 总计{configured_count}')
        else:
            self.status_label.setText('没有配置任何Cookie')
    
    '''clear_cookies'''
    def clear_cookies(self, source):
        # 清除特定源的cookie
        if source in self.custom_cookies:
            del self.custom_cookies[source]
        self.cookie_status[source] = 'unconfigured'
        self.update_checkbox_style(source)
        self.status_label.setText(f'已清除{source}的Cookie')
    
    '''clear_all_cookies'''
    def clear_all_cookies(self):
        # 清除所有cookie
        self.custom_cookies.clear()
        for source in self.src_names:
            self.cookie_status[source] = 'unconfigured'
            self.update_checkbox_style(source)
        self.status_label.setText('已清除所有Cookie')
    
    '''update_cookie_status_display'''
    def update_cookie_status_display(self):
        # 更新Cookie状态显示标签
        status_counts = {'valid': 0, 'invalid': 0, 'unconfigured': 0}
        for status in self.cookie_status.values():
            if status in status_counts:
                status_counts[status] += 1
        
        display_text = f'Cookie状态: 有效{status_counts["valid"]}, 无效{status_counts["invalid"]}, 未配置{status_counts["unconfigured"]}'
        self.cookie_status_label.setText(display_text)


'''tests'''
if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = MusicdlGUI()
    gui.show()
    sys.exit(app.exec_())