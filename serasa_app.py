import sys
import os
import math
import zipfile
import hashlib
import pandas as pd
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTextEdit, QMessageBox, QLabel, QSizePolicy, QFrame, QProgressBar
)
from PyQt5.QtGui import QIcon, QPixmap, QFont
from PyQt5.QtCore import Qt, QSize, QObject, QThread, pyqtSignal


LOGO_PATH = "C:/Users/c12511q/Documents/Serasa/icon/zip.png"

class ProcessWorker(QObject):
    """Worker que roda o processamento em background, com progresso e cancelamento."""
    log = pyqtSignal(str)
    progress = pyqtSignal(int)        # 0-100
    finished = pyqtSignal(pd.DataFrame)
    error = pyqtSignal(str)

    def __init__(self, zip_path, lote_size=10):
        super().__init__()
        self.zip_path = zip_path
        self.lote_size = lote_size
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            self.log.emit(">>> Iniciando processamento em background...")
            if not os.path.exists(self.zip_path):
                raise FileNotFoundError("Arquivo ZIP não encontrado.")

            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                arquivos = zip_ref.namelist()
                if not arquivos:
                    raise ValueError("ZIP vazio.")
                csv_nome = arquivos[0]
                self.log.emit(f">>> Lendo arquivo interno: {csv_nome}")
                with zip_ref.open(csv_nome) as arquivo_csv:
                    df = pd.read_csv(arquivo_csv)

            # preencher CPF
            def preencher_cpf(row):
                if pd.isna(row.get('CPF')) or row.get('CPF') == '' or row.get('CPF') == "'-":
                    if not pd.isna(row.get('CPF.1')) and row.get('CPF.1') != '' and row.get('CPF.1') != "'-":
                        return row.get('CPF.1')
                    elif not pd.isna(row.get('[RA] CPF')) and row.get('[RA] CPF') != '' and row.get('[RA] CPF') != "'-":
                        return row.get('[RA] CPF')
                return row.get('CPF')

            df['CPF'] = df.apply(preencher_cpf, axis=1)
            colunas_selecionadas = df.iloc[:, [5, 0, 3, 8]].copy()
            colunas_selecionadas.columns = ['CPF', 'ID', 'Data da Solicitacao', 'Formulario Ticket']

            self.log.emit(">>> Normalizando CPFs...")
            colunas_selecionadas['CPF'] = colunas_selecionadas['CPF'].fillna('').astype(str)
            colunas_selecionadas['CPF'] = (
                colunas_selecionadas['CPF']
                .str.replace(r'\D', '', regex=True)
                .str.zfill(11)
                .str[-11:]
            )

            colunas_selecionadas['cpf_valido'] = (
                colunas_selecionadas['CPF'].str.match(r'^\d{11}$') &
                (colunas_selecionadas['CPF'] != "00000000000")
            )

            colunas_selecionadas['Data da Solicitacao'] = pd.to_datetime(
                colunas_selecionadas['Data da Solicitacao'], errors='coerce'
            ).dt.strftime('%d/%m/%Y')

            colunas_selecionadas.insert(
                colunas_selecionadas.columns.get_loc('Data da Solicitacao') + 1,
                'Data da Resolucao', pd.NaT
            )

            def consultar_cpf_em_lote(cpf_list):
                headers = {
                    "X-ECS-APPLICATION-ID": "auth",
                    "Content-Type": "application/json"
                }
                url = "https://k8s-api-auth-prd.ecsbr.net/auth/user/batch/v2/users"
                payload = {"cpf": cpf_list}
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                if response.status_code == 200:
                    result = response.json()
                    users = result.get('users', [])
                    return [{'cpf': user['cpf'], 'userID': user['id'], 'name': user.get('name')} for user in users]
                else:
                    response.raise_for_status()

            cpfs = colunas_selecionadas.loc[colunas_selecionadas['cpf_valido'], 'CPF'].tolist()
            total_cpfs = len(cpfs)
            self.log.emit(f">>> CPFs válidos encontrados: {total_cpfs}")

            result_final = []
            if total_cpfs == 0:
                # nothing to do, emit progress 100
                self.progress.emit(100)
            else:
                blocos_cpfs = [cpfs[i:i+self.lote_size] for i in range(0, total_cpfs, self.lote_size)]
                total_blocos = len(blocos_cpfs)
                for idx, bloco in enumerate(blocos_cpfs, start=1):
                    if self._is_cancelled:
                        self.log.emit(">>> Processamento cancelado pelo usuário.")
                        self.progress.emit(0)
                        self.finished.emit(pd.DataFrame())
                        return

                    self.log.emit(f">>> Processando bloco {idx}/{total_blocos} ({len(bloco)} CPFs)...")
                    try:
                        result = consultar_cpf_em_lote(bloco)
                        result_final.extend(result)
                    except Exception as e_lote:
                        self.log.emit(f">>> Erro no lote, tentando fallback por CPF: {str(e_lote)}")
                        for cpf in bloco:
                            if self._is_cancelled:
                                self.log.emit(">>> Processamento cancelado durante fallback.")
                                self.progress.emit(0)
                                self.finished.emit(pd.DataFrame())
                                return
                            try:
                                base_url = 'https://k8s-api-auth-prd.ecsbr.net/auth/user-retrieve/ms-user/v2/user?cpf='
                                resp = requests.get(base_url + cpf, timeout=12)
                                resp = resp.json()
                                result_final.append({
                                    'cpf': cpf,
                                    'userID': resp.get('id'),
                                    'name': resp.get('name')
                                })
                            except Exception:
                                # ignora falhas individuais
                                continue

                    # atualiza progresso por blocos
                    pct = int((idx / total_blocos) * 100)
                    self.progress.emit(min(100, pct))

            # pós-processamento e merge
            result_final = pd.DataFrame(result_final)
            if not result_final.empty:
                result_final.columns = ['cpf', 'userID', 'name']
            else:
                result_final = pd.DataFrame(columns=['cpf', 'userID', 'name'])

            colunas_selecionadas.rename(columns={'CPF': 'cpf'}, inplace=True)
            df_merged = pd.merge(colunas_selecionadas, result_final, on='cpf', how='left')

            def calcular_sha256(userID):
                if pd.notna(userID):
                    return hashlib.sha256(str(userID).encode('utf-8')).hexdigest()
                else:
                    return None

            df_merged['account_id'] = df_merged['userID'].apply(calcular_sha256)
            df_merged['status'] = df_merged['name'].apply(lambda x: 'CADASTRADO' if pd.notna(x) else 'SEM CADASTRO')
            df_merged = df_merged.drop_duplicates()

            df_final = df_merged[['cpf', 'userID', 'account_id', 'status', 'ID', 'Data da Solicitacao', 'Data da Resolucao', 'Formulario Ticket']].copy()
            self.progress.emit(100)
            self.log.emit(">>> Processamento concluído com sucesso.")
            self.finished.emit(df_final)

        except Exception as e:
            self.error.emit(str(e))

class SerasaApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Serasa - Data Process")
        self.setWindowIcon(QIcon("C:/Users/c12511q/Documents/Serasa/icon/logo.png"))
        self.setGeometry(100, 100, 680, 560)

        self.zip_path = ""
        self.df_final = pd.DataFrame()
        self.worker_thread = None
        self.worker = None

        self.title_font = QFont("Segoe UI", 28, QFont.Bold)
        self.mono_font = QFont("Courier New", 10)

        self.root_layout = QVBoxLayout()
        self.root_layout.setContentsMargins(24, 18, 24, 18)
        self.root_layout.setSpacing(14)
        self.setLayout(self.root_layout)

        self._build_header()
        self._build_buttons_row()
        self._build_log_area_and_progress()
        self._apply_styles()

        self.log_message(">>> Iniciando script...")
        self.log_message(">>> Selecionando colunas por índice...")

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(12)
        logo_label = QLabel()
        logo_label.setFixedSize(96, 96)
        try:
            if os.path.exists(LOGO_PATH):
                pix = QPixmap(LOGO_PATH).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                logo_label.setPixmap(pix)
            else:
                raise FileNotFoundError
        except Exception:
            logo_label.setStyleSheet("background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #7b61ff, stop:1 #b89cff); border-radius: 12px;")
        header.addWidget(logo_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)

        title_and_sub = QVBoxLayout()
        title = QLabel("Serasa Data Processor")
        title.setFont(self.title_font)
        title.setStyleSheet("color: #241436;")
        title_and_sub.addWidget(title, alignment=Qt.AlignLeft)
        header.addLayout(title_and_sub)
        header.addStretch()
        self.root_layout.addLayout(header)

    def _build_buttons_row(self):
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        icon_select = QIcon("C:/Users/c12511q/Documents/Serasa/icon/open.png")
        icon_process = QIcon("C:/Users/c12511q/Documents/Serasa/icon/process.png")
        icon_export = QIcon("C:/Users/c12511q/Documents/Serasa/icon/export.png")
        icon_cancel = QIcon("C:/Users/c12511q/Documents/Serasa/icon/cancel.png")

        self.btn_select_zip = QPushButton("Selecionar ZIP")
        self.btn_select_zip.setIcon(icon_select)
        self.btn_select_zip.setIconSize(QSize(32, 32))
        self.btn_select_zip.setMinimumHeight(70)
        self.btn_select_zip.clicked.connect(self.select_zip)

        self.btn_process = QPushButton("Processar Dados")
        self.btn_process.setIcon(icon_process)
        self.btn_process.setIconSize(QSize(32, 32))
        self.btn_process.setMinimumHeight(70)
        self.btn_process.clicked.connect(self.start_processing_in_thread)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setIcon(icon_cancel)
        self.btn_cancel.setIconSize(QSize(32, 32))
        self.btn_cancel.setMinimumHeight(70)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_processing)

        self.btn_export = QPushButton("Exportar para Excel")
        self.btn_export.setIcon(icon_export)
        self.btn_export.setIconSize(QSize(32, 32))
        self.btn_export.setMinimumHeight(70)
        self.btn_export.clicked.connect(self.export_to_excel)

        for b in (self.btn_select_zip, self.btn_process, self.btn_cancel, self.btn_export):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn_row.addWidget(b)

        self.root_layout.addLayout(btn_row)

    def _build_log_area_and_progress(self):
        frame = QFrame()
        frame.setObjectName("logFrame")
        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(8)
        frame.setLayout(frame_layout)

        top_row = QHBoxLayout()
        info_label = QLabel()
        info_label.setFixedSize(24, 24)
        info_label.setPixmap(QPixmap("C:/Users/c12511q/Documents/Serasa/icon/inf.png").scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        top_row.addWidget(info_label, alignment=Qt.AlignTop)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(self.mono_font)
        self.log.setFrameStyle(QFrame.NoFrame)
        self.log.setStyleSheet("background: transparent;")
        top_row.addWidget(self.log)
        frame_layout.addLayout(top_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(20)
        frame_layout.addWidget(self.progress_bar)

        self.root_layout.addWidget(frame)

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background: #faf7fb;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #7b61ff, stop:1 #9b7bff);
                color: white;
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:disabled {
                background: #cfc4ff;
            }
            #logFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f2ecff, stop:1 #f7f3ff);
                border-radius: 12px;
                border: 1px solid #ddd3f2;
                min-height: 180px;
            }
            QTextEdit {
                background: transparent;
                color: #241436;
                padding: 6px;
            }
        """)

    def log_message(self, message):
        self.log.append(message)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def select_zip(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo ZIP", "", "ZIP Files (*.zip)")
        if file_path:
            self.zip_path = file_path
            self.log_message(f">>> ZIP selecionado: {self.zip_path}")

    def start_processing_in_thread(self):
        if not self.zip_path:
            QMessageBox.warning(self, "Aviso", "Selecione um arquivo ZIP primeiro.")
            return

        # desabilitar/ativar controles
        self.btn_process.setEnabled(False)
        self.btn_select_zip.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_message(">>> Iniciando worker...")

        # cria thread/worker
        self.worker_thread = QThread()
        self.worker = ProcessWorker(self.zip_path, lote_size=10)
        self.worker.moveToThread(self.worker_thread)

        # liga sinais
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_message)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)

        # cleanup quando terminar
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self.worker_thread.start()

    def cancel_processing(self):
        if self.worker:
            self.log_message(">>> Solicitado cancelamento...")
            self.worker.cancel()
            # desabilitar botão cancelar enquanto worker encerra
            self.btn_cancel.setEnabled(False)

    def on_worker_finished(self, df_result):
        self.df_final = df_result.copy() if not df_result.empty else pd.DataFrame()
        self.log_message(">>> Worker finalizado — df_final atualizado.")
        # reabilitar controles
        self.btn_process.setEnabled(True)
        self.btn_select_zip.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def on_worker_error(self, err_msg):
        self.log_message(f"Erro no worker: {err_msg}")
        QMessageBox.critical(self, "Erro", f"Erro ao processar: {err_msg}")
        self.btn_process.setEnabled(True)
        self.btn_select_zip.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(0)

    def export_to_excel(self):
        if self.df_final.empty:
            QMessageBox.warning(self, "Aviso", "Nenhum dado processado para exportar.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Salvar como", "", "Excel Files (*.xlsx)")
        if file_path:
            if not file_path.lower().endswith(".xlsx"):
                file_path += ".xlsx"
            self.df_final.to_excel(file_path, index=False)
            self.log_message(f">>> Arquivo exportado com sucesso: {file_path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SerasaApp()
    window.show()
    sys.exit(app.exec_())
