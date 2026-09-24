# -*- coding: utf-8 -*-
"""FreeNodesPro 桌面界面（PySide6）。

双击运行的 GUI：一键搜索测试节点、看结果、管理源、导出订阅。
所有耗时任务跑在后台线程，界面不卡。
"""

import datetime
import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem, QCheckBox,
    QLineEdit, QComboBox, QGroupBox, QFormLayout, QMessageBox, QHeaderView,
    QFileDialog, QPlainTextEdit,
)

import kernel as kernel_mod
import sources as sources_mod
from main import run as pipeline_run
from exporters import build_all


# 后台线程往界面发信号的桥梁（Qt 不允许在子线程直接改界面）
class LogBridge(QObject):
    line = Signal(str)
    progress = Signal(str)
    done = Signal(object, str)   # (info, out_dir) 或 (None, 错误信息)
    sources_changed = Signal()


def _open(path):
    """用资源管理器打开目录（用户好找导出的文件）。"""
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FreeNodesPro — 免费节点搜索订阅")
        self.resize(900, 640)
        self.worker = None
        self.out_dir = None
        self.last_info = None

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        # ---- 顶部：一键搜索 ----
        top = QGroupBox("搜索并测试节点")
        tl = QVBoxLayout(top)
        row = QHBoxLayout()
        self.btn_run = QPushButton("▶  搜索 + 测试")
        self.btn_run.setFont(QFont("", 12, QFont.Bold))
        self.btn_run.setMinimumHeight(40)
        self.btn_run.clicked.connect(self.start_run)
        self.btn_open = QPushButton("打开输出目录")
        self.btn_open.clicked.connect(lambda: self.out_dir and _open(self.out_dir))
        self.btn_open.setEnabled(False)
        row.addWidget(self.btn_run)
        row.addWidget(self.btn_open)
        row.addStretch()
        self.lbl_kernel = QLabel()
        tl.addLayout(row)
        tl.addWidget(self.lbl_kernel)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)   # 忙碌动画
        self.bar.setVisible(False)
        tl.addWidget(self.bar)
        self.lbl_status = QLabel("点「搜索 + 测试」开始。整个过程几分钟，不影响电脑。")
        tl.addWidget(self.lbl_status)

        # ---- 标签页 ----
        tabs = QTabWidget()
        tabs.addTab(self._tab_nodes(), "节点结果")
        tabs.addTab(self._tab_sources(), "源管理")
        tabs.addTab(self._tab_log(), "日志")
        lay.addWidget(top)
        lay.addWidget(tabs, 1)

        self.bridge = LogBridge()
        self.bridge.line.connect(self._log)
        self.bridge.progress.connect(self._set_status)
        self.bridge.done.connect(self._on_done)
        self.bridge.sources_changed.connect(self._reload_sources)

        self._refresh_kernel()
        self._reload_sources()

    # ---- 结果页 ----
    def _tab_nodes(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["节点", "地区", "延迟", "速度", "解锁", "来源"])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        l.addWidget(self.tbl)

        row = QHBoxLayout()
        b1 = QPushButton("导出 Clash")
        b2 = QPushButton("导出 sing-box")
        b3 = QPushButton("导出 base64")
        b4 = QPushButton("复制节点名")
        for b in (b1, b2, b3, b4):
            b.setEnabled(False)
        b1.clicked.connect(lambda: self._export("clash"))
        b2.clicked.connect(lambda: self._export("singbox"))
        b3.clicked.connect(lambda: self._export("base64"))
        b4.clicked.connect(self._copy_names)
        self.export_btns = [b1, b2, b3, b4]
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3); row.addStretch()
        row.addWidget(b4)
        l.addLayout(row)
        return w

    # ---- 源管理页 ----
    def _tab_sources(self):
        w = QWidget()
        l = QVBoxLayout(w)

        self.src_tbl = QTableWidget(0, 6)
        self.src_tbl.setHorizontalHeaderLabels(
            ["启用", "名字", "类型", "成功", "失败", "状态"])
        self.src_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.src_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.src_tbl.itemChanged.connect(self._on_src_toggle)
        l.addWidget(self.src_tbl)

        # 手动加源
        g = QGroupBox("手动添加源")
        gl = QFormLayout(g)
        self.in_name = QLineEdit()
        self.in_name.setPlaceholderText("随便起个名字")
        self.in_url = QLineEdit()
        self.in_url.setPlaceholderText("https://raw.githubusercontent.com/xxx/xxx/main/clash.yaml")
        self.in_kind = QComboBox()
        self.in_kind.addItems(["clash", "base64", "iplist", "iplist_tls"])
        self.in_kind.setCurrentText("clash")
        gl.addRow("名字", self.in_name)
        gl.addRow("链接", self.in_url)
        gl.addRow("类型", self.in_kind)
        br = QHBoxLayout()
        b_add = QPushButton("添加")
        b_add.clicked.connect(self._add_source)
        b_del = QPushButton("删除选中")
        b_del.clicked.connect(self._del_source)
        b_search = QPushButton("去 GitHub 搜同类源")
        b_search.clicked.connect(self._search_sources)
        br.addWidget(b_add); br.addWidget(b_del); br.addStretch(); br.addWidget(b_search)
        gl.addRow(br)
        l.addWidget(g)

        hint = QLabel(
            "类型说明：clash=clash 配置（质量最高）｜base64=v2ray 订阅｜"
            "iplist=明文 ip:port 代理列表｜iplist_tls=HTTPS 代理列表\n"
            "内置源删了也不怕，下次启动会自动回来；连续失败 3 次的源会自动降级。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        l.addWidget(hint)
        return w

    # ---- 日志页 ----
    def _tab_log(self):
        w = QWidget()
        l = QVBoxLayout(w)
        self.logview = QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setFont(QFont("Consolas", 9))
        l.addWidget(self.logview)
        return w

    # ---- 行为 ----
    def _refresh_kernel(self):
        v = kernel_mod.version()
        self.lbl_kernel.setText(
            f"内核：{v}" if v else
            "内核：未安装（首次搜索时会自动下载，约 20MB，只需一次）")
        self.lbl_kernel.setStyleSheet("color: gray;")

    def _log(self, msg):
        self.logview.appendPlainText(msg)
        self.logview.moveCursor(QTextCursor.End)

    def _set_status(self, msg):
        self.lbl_status.setText(msg)

    def start_run(self):
        if self.worker and self.worker.is_alive():
            return
        self.btn_run.setEnabled(False)
        self.bar.setVisible(True)
        self._set_status("正在搜索测试…")
        for b in self.export_btns:
            b.setEnabled(False)

        def on_log(m):
            self.bridge.line.emit(m)

        def on_prog(m):
            self.bridge.progress.emit(m)

        def work():
            try:
                info, out_dir = pipeline_run(on_log=on_log, on_progress=on_prog)
                self.bridge.done.emit(info, out_dir)
            except Exception as e:
                self.bridge.done.emit(None, f"失败：{e}")
            finally:
                self.bridge.sources_changed.emit()

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _on_done(self, info, out_dir_or_err):
        self.btn_run.setEnabled(True)
        self.bar.setVisible(False)
        if info is None:
            self._set_status(out_dir_or_err)
            self._log(out_dir_or_err)
            return
        self.last_info = info
        self.out_dir = out_dir_or_err
        self.btn_open.setEnabled(True)
        for b in self.export_btns:
            b.setEnabled(True)
        n = info.get("total", 0)
        self._set_status(f"完成：{n} 个节点已写入 {out_dir_or_err}")
        self._fill_nodes(info)

    def _fill_nodes(self, info):
        nodes = info.get("nodes", [])
        self.tbl.setRowCount(0)
        for p in nodes:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(p.get("name", ""))))
            self.tbl.setItem(r, 1, QTableWidgetItem(str(p.get("region", ""))))
            d = p.get("delay")
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{d}ms" if d else "-"))
            k = p.get("kbps")
            self.tbl.setItem(r, 3, QTableWidgetItem(
                f"{k/1024:.1f}MB/s" if k and k >= 1024 else
                (f"{k:.0f}KB/s" if k else "-")))
            ul = p.get("unlock") or {}
            self.tbl.setItem(r, 4, QTableWidgetItem(
                "".join(t for t, v in ul.items() if v)))
            self.tbl.setItem(r, 5, QTableWidgetItem(str(p.get("src", ""))))

    def _export(self, kind):
        if not self.last_info:
            return
        # 直接用已有的最终节点列表重新导出
        out = self.out_dir or os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "FreeNodesPro", "out")
        try:
            build_all(self.last_info.get("nodes_raw", []), out)
        except Exception as e:
            QMessageBox.warning(self, "导出", f"导出失败：{e}")
            return
        _open(os.path.join(out, {"clash": "clash.yaml",
                                 "singbox": "singbox.json",
                                 "base64": "v2ray.txt"}[kind]))

    def _copy_names(self):
        rows = {i.row() for i in self.tbl.selectedIndexes()}
        if not rows:
            return
        names = [self.tbl.item(r, 0).text() for r in sorted(rows)]
        QApplication.clipboard().setText("\n".join(names))

    # ---- 源管理 ----
    def _reload_sources(self):
        srcs = sources_mod.list_sources()
        self.src_tbl.blockSignals(True)
        self.src_tbl.setRowCount(0)
        for s in srcs:
            r = self.src_tbl.rowCount()
            self.src_tbl.insertRow(r)
            cb = QCheckBox()
            cb.setChecked(bool(s.get("enabled", True)))
            cb.setProperty("url", s["url"])
            self.src_tbl.setCellWidget(r, 0, cb)
            self.src_tbl.setItem(r, 1, QTableWidgetItem(s["name"]))
            self.src_tbl.setItem(r, 2, QTableWidgetItem(s.get("kind", "")))
            self.src_tbl.setItem(r, 3, QTableWidgetItem(str(s.get("ok", 0))))
            self.src_tbl.setItem(r, 4, QTableWidgetItem(str(s.get("fail", 0))))
            if not s.get("enabled", True):
                st = "已停用（连续失败，1 天后自动重试）"
            elif s.get("ok", 0) == 0 and s.get("fail", 0) == 0:
                st = "还没测试过"
            else:
                st = "正常"
            self.src_tbl.setItem(r, 5, QTableWidgetItem(st))
        self.src_tbl.blockSignals(False)

    def _on_src_toggle(self, item):
        cb = self.src_tbl.cellWidget(item.row(), 0)
        if cb is None:
            return
        sources_mod.set_enabled(cb.property("url"), cb.isChecked())

    def _add_source(self):
        ok, msg = sources_mod.add_source(
            self.in_name.text().strip(),
            self.in_url.text().strip(),
            self.in_kind.currentText())
        if ok:
            self.in_name.clear(); self.in_url.clear()
            self._reload_sources()
        QMessageBox.information(self, "添加源", msg)

    def _del_source(self):
        rows = {i.row() for i in self.src_tbl.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "删除源", "先在表格里选中一行")
            return
        urls = [self.src_tbl.cellWidget(r, 0).property("url") for r in rows]
        n = 0
        for u in urls:
            if u and sources_mod.remove_source(u)[0]:
                n += 1
        self._reload_sources()
        QMessageBox.information(self, "删除源", f"已处理 {n} 个源")

    def _search_sources(self):
        self._set_status("正在 GitHub 搜索同类源…")
        def work():
            added = sources_mod.find_new_sources(on_log=lambda m: self.bridge.line.emit(m))
            self.bridge.line.emit(f"搜索补位完成：新增 {len(added)} 个源")
            self.bridge.sources_changed.emit()
            self.bridge.progress.emit("就绪")
        threading.Thread(target=work, daemon=True).start()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FreeNodesPro")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
