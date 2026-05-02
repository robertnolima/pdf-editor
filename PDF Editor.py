import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import fitz  # PyMuPDF
from PIL import Image, ImageTk, ImageDraw
import io
import threading
import queue
import collections

# ── Constantes de performance ───────────────────────────────────────────────
MAX_CACHE    = 60    # máx. imagens PIL em memória (LRU)
NUM_WORKERS  = 2    # threads de renderização paralelas

# ── Constantes de tema ──────────────────────────────────────────────────────
THUMB_MIN     = 80
THUMB_MAX     = 400
THUMB_DEFAULT = 160

COR_BG       = '#1a1a2e'
COR_TOOLBAR  = '#16213e'
COR_CARD     = '#0f3460'
COR_CARD_BG  = '#1a1a2e'
COR_SEL      = '#e94560'
COR_SEL_BD   = '#ff6b8a'
COR_TEXTO    = '#e0e0e0'
COR_TEXTO2   = '#a0a0b0'
COR_ARQUIVO  = '#0e639c'
COR_SALVAR   = '#16825d'
COR_EDICAO   = '#7b2d8b'
COR_EXCLUIR  = '#c0392b'
COR_INSERIR  = '#1a6b3c'
COR_SEL_BTN  = '#2c3e50'
COR_ROT_L    = '#5b4a9c'
COR_ROT_R    = '#4a6fa5'
COR_ROT_360  = '#2c7a7b'
COR_CROP     = '#7a4f2c'
COR_HOVER_BD = '#3a6ea8'


# ── Widget de Miniatura ──────────────────────────────────────────────────────
class CardMiniatura(tk.Frame):
    def __init__(self, parent, pos, img_placeholder, callbacks):
        super().__init__(parent, bg=COR_CARD_BG, padx=4, pady=4, cursor='hand2')
        self.pos         = pos
        self.selecionada = False
        self.callbacks   = callbacks
        self._drag_ativo = False
        self._px = self._py = 0

        # Borda com efeito de card
        self.borda = tk.Frame(self, bg='#2a3f5f', relief='flat', bd=0)
        self.borda.pack(expand=True, fill=tk.BOTH)

        # Indicador de seleção (topo)
        self.barra_sel = tk.Frame(self.borda, bg='#2a3f5f', height=3)
        self.barra_sel.pack(fill=tk.X)

        self.lbl_img = tk.Label(self.borda, image=img_placeholder,
                                bg='#1e2d45', cursor='hand2')
        self.lbl_img.pack(padx=2, pady=(2, 0))

        # Rodapé do card
        self.rodape = tk.Frame(self.borda, bg='#1e2d45')
        self.rodape.pack(fill=tk.X)

        self.lbl_num = tk.Label(self.rodape, text=f"Pág {pos + 1}",
                                bg='#1e2d45', fg=COR_TEXTO2,
                                font=('Segoe UI', 8, 'bold'), pady=4)
        self.lbl_num.pack(side=tk.LEFT, padx=6)

        self.lbl_rot = tk.Label(self.rodape, text="",
                                bg='#1e2d45', fg='#7a9ccc',
                                font=('Segoe UI', 7))
        self.lbl_rot.pack(side=tk.RIGHT, padx=6)

        self._bind_all()

    def _bind_all(self):
        widgets = [self, self.borda, self.lbl_img, self.lbl_num,
                   self.lbl_rot, self.rodape, self.barra_sel]
        for w in widgets:
            w.bind('<Button-1>',         self._click)
            w.bind('<Control-Button-1>', self._ctrl_click)
            w.bind('<Shift-Button-1>',   self._shift_click)
            w.bind('<Button-3>',         self._right_click)
            w.bind('<ButtonPress-1>',    self._press)
            w.bind('<B1-Motion>',        self._move)
            w.bind('<ButtonRelease-1>',  self._release)
            w.bind('<Enter>',            self._hover_in)
            w.bind('<Leave>',            self._hover_out)

    def set_imagem(self, img_tk):
        self.lbl_img.config(image=img_tk)
        self.lbl_img.image = img_tk

    def set_rotacao_label(self, graus):
        if graus == 0:
            self.lbl_rot.config(text="")
        else:
            self.lbl_rot.config(text=f"↻{graus}°")

    def set_selecionada(self, val):
        self.selecionada = val
        if val:
            self.config(bg=COR_SEL)
            self.borda.config(bg=COR_SEL_BD)
            self.barra_sel.config(bg=COR_SEL)
            self.lbl_img.config(bg='#3d1a24')
            self.lbl_num.config(bg='#3d1a24', fg='white')
            self.lbl_rot.config(bg='#3d1a24')
            self.rodape.config(bg='#3d1a24')
        else:
            self.config(bg=COR_CARD_BG)
            self.borda.config(bg='#2a3f5f')
            self.barra_sel.config(bg='#2a3f5f')
            self.lbl_img.config(bg='#1e2d45')
            self.lbl_num.config(bg='#1e2d45', fg=COR_TEXTO2)
            self.lbl_rot.config(bg='#1e2d45')
            self.rodape.config(bg='#1e2d45')

    # ── Eventos ──
    def _click(self, e):
        cb = self.callbacks.get('click')
        if cb: cb(self.pos)

    def _ctrl_click(self, e):
        cb = self.callbacks.get('ctrl_click')
        if cb: cb(self.pos)
        return 'break'

    def _shift_click(self, e):
        cb = self.callbacks.get('shift_click')
        if cb: cb(self.pos)
        return 'break'

    def _right_click(self, e):
        cb = self.callbacks.get('right_click')
        if cb: cb(self.pos, e)

    def _press(self, e):
        self._px, self._py = e.x, e.y
        self._drag_ativo = False

    def _move(self, e):
        if not self._drag_ativo:
            if abs(e.x - self._px) > 5 or abs(e.y - self._py) > 5:
                self._drag_ativo = True
                cb = self.callbacks.get('drag_start')
                if cb: cb(self.pos, e)
        if self._drag_ativo:
            cb = self.callbacks.get('drag_move')
            if cb: cb(self.pos, e)

    def _release(self, e):
        if self._drag_ativo:
            self._drag_ativo = False
            cb = self.callbacks.get('drag_end')
            if cb: cb(self.pos, e)

    def _hover_in(self, e):
        if not self.selecionada:
            self.borda.config(bg=COR_HOVER_BD)

    def _hover_out(self, e):
        if not self.selecionada:
            self.borda.config(bg='#2a3f5f')


# ── Janela de Crop Avançada ──────────────────────────────────────────────────
class JanelaCrop(tk.Toplevel):
    def __init__(self, parent, img_pil, escala, idx_orig, pos, callback_apply):
        super().__init__(parent)
        self.title(f"✂ Recortar — Página {pos + 1}")
        self.configure(bg='#1a1a2e')
        self.grab_set()
        self.resizable(True, True)

        self.img_pil       = img_pil
        self.escala        = escala
        self.idx_orig      = idx_orig
        self.pos           = pos
        self.callback_apply = callback_apply

        self._x0 = self._y0 = 0
        self._x1 = self._y1 = 0
        self._rect_id  = None
        self._mask_ids = []
        self._dragging = False
        self._has_sel  = False

        self._build_ui()
        self._center_window()

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg='#16213e', pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="✂  Recortar Página",
                 bg='#16213e', fg='white',
                 font=('Segoe UI', 13, 'bold')).pack(side=tk.LEFT, padx=15)
        tk.Label(hdr,
                 text="Clique e arraste para selecionar a área de recorte",
                 bg='#16213e', fg='#8888aa',
                 font=('Segoe UI', 9)).pack(side=tk.LEFT, padx=10)

        # Info de coordenadas
        self.lbl_coords = tk.Label(self, text="Selecione uma área",
                                   bg='#1a1a2e', fg='#7a9ccc',
                                   font=('Segoe UI', 9))
        self.lbl_coords.pack(pady=(6, 2))

        # Canvas com scroll
        frame_cv = tk.Frame(self, bg='#0d0d1a')
        frame_cv.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        sb_v = ttk.Scrollbar(frame_cv, orient=tk.VERTICAL)
        sb_v.pack(side=tk.RIGHT, fill=tk.Y)
        sb_h = ttk.Scrollbar(frame_cv, orient=tk.HORIZONTAL)
        sb_h.pack(side=tk.BOTTOM, fill=tk.X)

        self.cv = tk.Canvas(frame_cv,
                            width=min(self.img_pil.width, 900),
                            height=min(self.img_pil.height, 700),
                            bg='#0d0d1a', cursor='crosshair',
                            highlightthickness=0,
                            xscrollcommand=sb_h.set,
                            yscrollcommand=sb_v.set)
        self.cv.pack(fill=tk.BOTH, expand=True)
        sb_v.config(command=self.cv.yview)
        sb_h.config(command=self.cv.xview)

        self._img_tk = ImageTk.PhotoImage(self.img_pil)
        self.cv.create_image(0, 0, anchor='nw', image=self._img_tk)
        self.cv.configure(scrollregion=(0, 0, self.img_pil.width, self.img_pil.height))

        self.cv.bind('<ButtonPress-1>',  self._press)
        self.cv.bind('<B1-Motion>',      self._drag)
        self.cv.bind('<ButtonRelease-1>', self._release_drag)

        # Botões
        fr_btn = tk.Frame(self, bg='#16213e', pady=10)
        fr_btn.pack(fill=tk.X)

        botoes = [
            ("✓  Aplicar Recorte",  self._aplicar,  '#16825d'),
            ("✕  Limpar Seleção",   self._limpar,   '#c0392b'),
            ("   Cancelar",         self.destroy,   '#2c3e50'),
        ]
        for txt, cmd, cor in botoes:
            btn = tk.Button(fr_btn, text=txt, command=cmd,
                           bg=cor, fg='white', relief=tk.FLAT,
                           padx=16, pady=8,
                           font=('Segoe UI', 10, 'bold'),
                           cursor='hand2', bd=0)
            btn.pack(side=tk.LEFT, padx=8, pady=6)
            btn.bind('<Enter>', lambda e, b=btn, c=cor: b.config(bg=self._clarear(c)))
            btn.bind('<Leave>', lambda e, b=btn, c=cor: b.config(bg=c))

    def _clarear(self, cor):
        try:
            h = cor.lstrip('#')
            r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
            return f'#{min(255,r+35):02x}{min(255,g+35):02x}{min(255,b+35):02x}'
        except:
            return cor

    def _center_window(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"+{x}+{y}")

    def _press(self, e):
        self._x0 = self.cv.canvasx(e.x)
        self._y0 = self.cv.canvasy(e.y)
        self._dragging = True
        self._has_sel  = False
        self._clear_drawing()

    def _drag(self, e):
        if not self._dragging:
            return
        x1 = self.cv.canvasx(e.x)
        y1 = self.cv.canvasy(e.y)
        self._clear_drawing()
        self._draw_selection(self._x0, self._y0, x1, y1)
        # Atualiza coordenadas em px reais
        rx0 = int(min(self._x0, x1) / self.escala)
        ry0 = int(min(self._y0, y1) / self.escala)
        rx1 = int(max(self._x0, x1) / self.escala)
        ry1 = int(max(self._y0, y1) / self.escala)
        w = rx1 - rx0
        h = ry1 - ry0
        self.lbl_coords.config(
            text=f"Área: ({rx0}, {ry0}) → ({rx1}, {ry1})   |   {w} × {h} px")

    def _release_drag(self, e):
        if not self._dragging:
            return
        self._dragging = False
        self._x1 = self.cv.canvasx(e.x)
        self._y1 = self.cv.canvasy(e.y)
        if abs(self._x1 - self._x0) > 5 and abs(self._y1 - self._y0) > 5:
            self._has_sel = True

    def _clear_drawing(self):
        if self._rect_id:
            self.cv.delete(self._rect_id)
            self._rect_id = None
        for mid in self._mask_ids:
            self.cv.delete(mid)
        self._mask_ids = []

    def _draw_selection(self, x0, y0, x1, y1):
        lx0, ly0 = min(x0, x1), min(y0, y1)
        lx1, ly1 = max(x0, x1), max(y0, y1)
        W = self.img_pil.width
        H = self.img_pil.height

        # Máscara escura fora da seleção
        regioes = [
            (0, 0, W, ly0),       # topo
            (0, ly1, W, H),       # fundo
            (0, ly0, lx0, ly1),   # esquerda
            (lx1, ly0, W, ly1),   # direita
        ]
        for rx0, ry0, rx1, ry1 in regioes:
            if rx1 > rx0 and ry1 > ry0:
                mid = self.cv.create_rectangle(
                    rx0, ry0, rx1, ry1,
                    fill='black', stipple='gray50',
                    outline='', tags='mask')
                self._mask_ids.append(mid)

        # Borda de seleção animada
        self._rect_id = self.cv.create_rectangle(
            lx0, ly0, lx1, ly1,
            outline='#ff4d6d', width=2, dash=(8, 4))

        # Alças nos cantos
        size = 6
        corners = [(lx0, ly0), (lx1, ly0), (lx0, ly1), (lx1, ly1)]
        for cx, cy in corners:
            mid = self.cv.create_rectangle(
                cx - size, cy - size, cx + size, cy + size,
                fill='#ff4d6d', outline='white', width=1)
            self._mask_ids.append(mid)

    def _aplicar(self):
        if not self._has_sel:
            messagebox.showwarning("Aviso",
                "Selecione uma área antes de aplicar.", parent=self)
            return
        x0 = min(self._x0, self._x1)
        y0 = min(self._y0, self._y1)
        x1 = max(self._x0, self._x1)
        y1 = max(self._y0, self._y1)
        rect_fitz = fitz.Rect(x0 / self.escala, y0 / self.escala,
                               x1 / self.escala, y1 / self.escala)
        self.callback_apply(self.idx_orig, self.pos, rect_fitz)
        self.destroy()

    def _limpar(self):
        self._clear_drawing()
        self._has_sel = False
        self.lbl_coords.config(text="Seleção removida")
        self.callback_apply(self.idx_orig, self.pos, None)  # None = remove crop
        self.destroy()


# ── Aplicação Principal ──────────────────────────────────────────────────────
class PDFEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Editor Pro")
        self.root.state('zoomed')
        self.root.configure(bg=COR_BG)

        # Estado do documento
        self.doc             = None
        self.caminho_arquivo = None
        self.ordem_paginas   = []   # índices originais na ordem atual
        self.rotacoes        = {}   # {idx_orig: graus acumulados}
        self.crops           = {}   # {idx_orig: fitz.Rect}
        self.selecionadas    = set()
        self.ultima_sel      = None

        # Cache LRU — evita estouro de memória em PDFs grandes
        self.cache_pil  = collections.OrderedDict()  # {(idx,rot,larg): PIL.Image}
        self.imagens_tk = {}   # {pos: ImageTk.PhotoImage}
        self.cards      = {}   # {pos: CardMiniatura}

        # Concorrência
        self._fitz_lock      = threading.Lock()
        self._workers_ativos = 0

        # Drag & drop
        self._fantasma    = None
        self._drag_origem = None

        # Renderização assíncrona
        self._fila       = queue.Queue()
        self._cancelar   = False

        # Debounce
        self._resize_id = None
        self._slider_id = None

        # Tamanho das miniaturas
        self.largura_thumb = tk.IntVar(value=THUMB_DEFAULT)

        # Placeholder
        self._placeholder = self._make_placeholder(THUMB_DEFAULT,
                                                    int(THUMB_DEFAULT * 1.41))
        self._construir_ui()

    # ── Placeholder ─────────────────────────────────────────────────────────
    def _make_placeholder(self, w, h):
        img = Image.new('RGB', (w, h), '#1e2d45')
        draw = ImageDraw.Draw(img)
        # Grade sutil
        for x in range(0, w, 20):
            draw.line([(x, 0), (x, h)], fill='#243550', width=1)
        for y in range(0, h, 20):
            draw.line([(0, y), (w, y)], fill='#243550', width=1)
        return ImageTk.PhotoImage(img)

    # ── Construção da UI ─────────────────────────────────────────────────────
    def _construir_ui(self):
        # ── Toolbar principal ────────────────────────────────────────────────
        self.toolbar = tk.Frame(self.root, bg=COR_TOOLBAR, pady=6)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        # Grupo: Arquivo
        self._grupo_label("ARQUIVO")
        self._tbtn("📂  Abrir PDF",    self.abrir_pdf,      COR_ARQUIVO)
        self._tbtn("💾  Salvar Como",  self.salvar_como,    COR_SALVAR)
        self._tsep()

        # Grupo: Seleção
        self._grupo_label("SELEÇÃO")
        self._tbtn("☑  Todos",         self.selecionar_tudo,   COR_SEL_BTN)
        self._tbtn("⊡  Inverter",      self.inverter_selecao,  COR_SEL_BTN)
        self._tsep()

        # Grupo: Rotação
        self._grupo_label("ROTAÇÃO")
        self._tbtn("⟲  90° Esq.",      lambda: self.girar(-90),    COR_ROT_L)
        self._tbtn("⟳  90° Dir.",      lambda: self.girar(90),     COR_ROT_R)
        self._tbtn("↺  180°",          lambda: self.girar(180),    COR_ROT_360)
        self._tbtn("🔄  360°",         lambda: self.girar(360),    COR_ROT_360)
        self._tsep()

        # Grupo: Edição
        self._grupo_label("EDIÇÃO")
        self._tbtn("✂  Recortar",      self._crop_selecionada,  COR_CROP)
        self._tbtn("➕  Inserir PDF",  self.inserir_pdf,        COR_INSERIR)
        self._tbtn("🗑  Excluir",      self.excluir,            COR_EXCLUIR)
        self._tsep()

        # Zoom / tamanho
        tk.Label(self.toolbar, text="Zoom:", bg=COR_TOOLBAR,
                 fg=COR_TEXTO2, font=('Segoe UI', 8, 'bold')).pack(
                     side=tk.LEFT, padx=(8, 2))

        ttk.Scale(self.toolbar, from_=THUMB_MIN, to=THUMB_MAX,
                  orient=tk.HORIZONTAL, variable=self.largura_thumb,
                  length=130, command=self._slider_mudou).pack(side=tk.LEFT, padx=4)

        self.lbl_tamanho = tk.Label(self.toolbar, text=f"{THUMB_DEFAULT}px",
                                    bg=COR_TOOLBAR, fg=COR_TEXTO2,
                                    font=('Segoe UI', 8), width=5)
        self.lbl_tamanho.pack(side=tk.LEFT)
        self._tsep()

        # Informações
        self.lbl_info = tk.Label(self.toolbar, text="Nenhum PDF aberto",
                                 bg=COR_TOOLBAR, fg='#556080',
                                 font=('Segoe UI', 9))
        self.lbl_info.pack(side=tk.LEFT, padx=10)

        # Barra de progresso (oculta)
        self.progress = ttk.Progressbar(self.toolbar, mode='determinate',
                                        length=120)

        # ── Barra de status ──────────────────────────────────────────────────
        self.status_bar = tk.Frame(self.root, bg='#0d0d1a', height=24)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_status = tk.Label(self.status_bar, text="Pronto",
                                   bg='#0d0d1a', fg='#556080',
                                   font=('Segoe UI', 8), anchor='w')
        self.lbl_status.pack(side=tk.LEFT, padx=10, fill=tk.X)

        # ── Área de scroll ───────────────────────────────────────────────────
        area = tk.Frame(self.root, bg=COR_BG)
        area.pack(fill=tk.BOTH, expand=True)

        sb_v = ttk.Scrollbar(area, orient=tk.VERTICAL)
        sb_v.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(area, bg=COR_BG,
                                yscrollcommand=sb_v.set,
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        sb_v.config(command=self.canvas.yview)

        self.frame_grade = tk.Frame(self.canvas, bg=COR_BG)
        self._win_id = self.canvas.create_window((0, 0),
                                                  window=self.frame_grade,
                                                  anchor='nw')
        self.frame_grade.bind('<Configure>', self._on_frame_cfg)
        self.canvas.bind('<Configure>',      self._on_canvas_cfg)
        self.canvas.bind('<MouseWheel>',     self._scroll)
        self.frame_grade.bind('<MouseWheel>', self._scroll)
        self.root.bind('<MouseWheel>',        self._scroll)

        # Atalhos de teclado
        self.root.bind('<Delete>',          lambda e: self.excluir())
        self.root.bind('<Control-a>',       lambda e: self.selecionar_tudo())
        self.root.bind('<Control-o>',       lambda e: self.abrir_pdf())
        self.root.bind('<Control-s>',       lambda e: self.salvar_como())

        # Mensagem de boas-vindas
        self._mostrar_boas_vindas()

    def _grupo_label(self, texto):
        tk.Label(self.toolbar, text=texto, bg=COR_TOOLBAR,
                 fg='#3a4f6e', font=('Segoe UI', 7, 'bold')).pack(
                     side=tk.LEFT, padx=(10, 2))

    def _tbtn(self, texto, cmd, cor):
        def clarear(c):
            try:
                h = c.lstrip('#')
                r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
                return f'#{min(255,r+40):02x}{min(255,g+40):02x}{min(255,b+40):02x}'
            except:
                return c
        btn = tk.Button(self.toolbar, text=texto, command=cmd, bg=cor,
                        fg='white', relief=tk.FLAT, padx=9, pady=5,
                        cursor='hand2', font=('Segoe UI', 9, 'bold'),
                        activebackground=clarear(cor), activeforeground='white',
                        bd=0, highlightthickness=0)
        btn.pack(side=tk.LEFT, padx=2)
        btn.bind('<Enter>', lambda e: btn.config(bg=clarear(cor)))
        btn.bind('<Leave>', lambda e: btn.config(bg=cor))
        return btn

    def _tsep(self):
        tk.Frame(self.toolbar, bg='#2a3f5f', width=1
                 ).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)

    def _mostrar_boas_vindas(self):
        """Exibe mensagem de boas-vindas na área de miniaturas."""
        fr = tk.Frame(self.frame_grade, bg=COR_BG)
        fr.pack(expand=True, pady=80)

        tk.Label(fr, text="📄", bg=COR_BG, fg='#2a3f5f',
                 font=('Segoe UI', 64)).pack()
        tk.Label(fr, text="PDF Editor Pro",
                 bg=COR_BG, fg='#3a5070',
                 font=('Segoe UI', 22, 'bold')).pack(pady=(10, 4))
        tk.Label(fr,
                 text="Abra um PDF para começar\n(Ctrl+O ou clique em \"Abrir PDF\")",
                 bg=COR_BG, fg='#2a3f5f',
                 font=('Segoe UI', 11),
                 justify='center').pack()
        self._boas_vindas_frame = fr

    # ── Eventos de layout ────────────────────────────────────────────────────
    def _on_frame_cfg(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_cfg(self, e):
        self.canvas.itemconfig(self._win_id, width=e.width)
        if self._resize_id:
            self.root.after_cancel(self._resize_id)
        self._resize_id = self.root.after(200, self._reorganizar)

    def _scroll(self, e):
        self.canvas.yview_scroll(-1 * (e.delta // 120), 'units')
        # Ao rolar, agenda re-priorização das páginas visíveis
        if hasattr(self, '_scroll_id') and self._scroll_id:
            self.root.after_cancel(self._scroll_id)
        self._scroll_id = self.root.after(400, self._reprioritizar_visiveis)

    def _slider_mudou(self, val):
        self.lbl_tamanho.config(text=f"{int(float(val))}px")
        if self._slider_id:
            self.root.after_cancel(self._slider_id)
        self._slider_id = self.root.after(300, self._reorganizar)

    def _set_status(self, msg):
        self.lbl_status.config(text=msg)

    # ── Abrir / Salvar ───────────────────────────────────────────────────────
    def abrir_pdf(self):
        caminho = filedialog.askopenfilename(
            filetypes=[("Arquivos PDF", "*.pdf")], title="Abrir PDF")
        if not caminho:
            return
        try:
            if self.doc:
                self.doc.close()
            self.doc             = fitz.open(caminho)
            self.caminho_arquivo = caminho
            self.ordem_paginas   = list(range(len(self.doc)))
            self.rotacoes        = {}
            self.crops           = {}
            self.selecionadas    = set()
            self.ultima_sel      = None
            self.cache_pil.clear()
            nome = caminho.replace('\\', '/').split('/')[-1]
            self.root.title(f"PDF Editor Pro — {nome}")
            self._set_status(f"Aberto: {nome}  ({len(self.doc)} páginas)")
            # Remove boas-vindas se existir
            if hasattr(self, '_boas_vindas_frame'):
                try:
                    self._boas_vindas_frame.destroy()
                except:
                    pass
            self._iniciar_renderizacao()
        except Exception as ex:
            messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{ex}")

    def salvar_como(self):
        if not self.doc:
            messagebox.showwarning("Aviso", "Nenhum PDF aberto.")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")],
            title="Salvar PDF Como")
        if not caminho:
            return
        try:
            self._set_status("Salvando PDF...")
            novo = fitz.open()
            for idx_orig in self.ordem_paginas:
                novo.insert_pdf(self.doc, from_page=idx_orig, to_page=idx_orig)
                pag = novo.load_page(novo.page_count - 1)
                rot_extra = self.rotacoes.get(idx_orig, 0)
                if rot_extra:
                    pag.set_rotation((pag.rotation + rot_extra) % 360)
                if idx_orig in self.crops:
                    pag.set_cropbox(self.crops[idx_orig])
            novo.save(caminho)
            novo.close()
            nome = caminho.replace('\\', '/').split('/')[-1]
            self._set_status(f"Salvo: {nome}")
            messagebox.showinfo("Sucesso", f"PDF salvo em:\n{caminho}")
        except Exception as ex:
            messagebox.showerror("Erro", f"Erro ao salvar:\n{ex}")

    # ── Renderização assíncrona (otimizada para PDFs grandes) ─────────────────
    def _iniciar_renderizacao(self):
        """Inicia renderização com prioridade nas páginas visíveis."""
        self._cancelar = True
        # Aguarda workers pararem
        self.root.after(80, self._iniciar_renderizacao_real)

    def _iniciar_renderizacao_real(self):
        self._fila = queue.Queue()

        for w in self.frame_grade.winfo_children():
            w.destroy()
        self.cards.clear()
        self.imagens_tk.clear()

        if not self.ordem_paginas:
            return

        largura = self.largura_thumb.get()
        self._placeholder = self._make_placeholder(largura, int(largura * 1.41))
        colunas = self._calcular_colunas()

        for pos, idx_orig in enumerate(self.ordem_paginas):
            card = CardMiniatura(self.frame_grade, pos, self._placeholder,
                                 self._callbacks())
            linha = pos // colunas
            col   = pos % colunas
            card.grid(row=linha, column=col, padx=8, pady=8, sticky='n')
            self.cards[pos] = card
            rot = self.rotacoes.get(idx_orig, 0)
            card.set_rotacao_label(rot)

        for c in range(colunas):
            self.frame_grade.columnconfigure(c, weight=1)

        total = len(self.ordem_paginas)
        self.progress.config(maximum=total, value=0)
        self.progress.pack(side=tk.LEFT, padx=8)
        self._render_total    = total
        self._render_prontos  = 0

        self._cancelar = False
        self._workers_ativos = 0

        # Monta fila priorizada: visíveis primeiro, resto na sequência
        visiveis = self._posicoes_visiveis()
        ordem = list(visiveis) + [p for p in range(total) if p not in visiveis]
        fila_trabalho = queue.Queue()
        for pos in ordem:
            fila_trabalho.put(pos)

        for _ in range(NUM_WORKERS):
            self._workers_ativos += 1
            t = threading.Thread(
                target=self._worker_render,
                args=(largura, fila_trabalho),
                daemon=True)
            t.start()

        self.root.after(50, self._processar_fila)

    def _posicoes_visiveis(self):
        """Retorna set de posições cujos cards estão na área visível do canvas."""
        visiveis = set()
        try:
            cy0, cy1 = self.canvas.yview()
            total_h  = self.frame_grade.winfo_height()
            if total_h < 1:
                return set(range(min(20, len(self.ordem_paginas))))
            y_top    = cy0 * total_h
            y_bot    = cy1 * total_h
            for pos, card in self.cards.items():
                try:
                    cy = card.winfo_y()
                    ch = card.winfo_height()
                    if cy + ch >= y_top and cy <= y_bot:
                        visiveis.add(pos)
                except Exception:
                    pass
        except Exception:
            pass
        # Se não conseguiu determinar, assume as primeiras 20
        if not visiveis:
            return set(range(min(20, len(self.ordem_paginas))))
        return visiveis

    def _reprioritizar_visiveis(self):
        """Ao rolar, renderiza páginas ainda sem imagem que ficaram visíveis."""
        if not self.doc:
            return
        largura   = self.largura_thumb.get()
        pendentes = []  # páginas visíveis sem imagem que precisam ser renderizadas
        for pos in self._posicoes_visiveis():
            if pos in self.imagens_tk:
                continue  # já tem imagem
            if pos >= len(self.ordem_paginas):
                continue
            idx_orig = self.ordem_paginas[pos]
            rot      = self.rotacoes.get(idx_orig, 0)
            chave    = (idx_orig, rot, largura)
            if chave in self.cache_pil:
                # Já no cache — aplica direto
                img_tk = ImageTk.PhotoImage(self.cache_pil[chave])
                self.imagens_tk[pos] = img_tk
                if pos in self.cards:
                    self.cards[pos].set_imagem(img_tk)
            else:
                # Não está no cache — precisa renderizar
                pendentes.append(pos)

        if pendentes:
            # Renderiza as páginas pendentes em thread separada
            fila_rec = queue.Queue()
            for pos in pendentes:
                fila_rec.put(pos)
            t = threading.Thread(
                target=self._worker_render,
                args=(largura, fila_rec),
                daemon=True)
            t.start()

    def _cache_put(self, chave, img):
        """Insere no cache LRU, evictando o mais antigo se necessário."""
        if chave in self.cache_pil:
            self.cache_pil.move_to_end(chave)
        else:
            self.cache_pil[chave] = img
            if len(self.cache_pil) > MAX_CACHE:
                self.cache_pil.popitem(last=False)  # remove o mais antigo

    def _worker_render(self, largura, fila_trabalho):
        """Worker thread: cada uma processa itens da fila de trabalho."""
        while not self._cancelar:
            try:
                pos = fila_trabalho.get_nowait()
            except queue.Empty:
                break
            if pos >= len(self.ordem_paginas):
                continue
            idx_orig = self.ordem_paginas[pos]
            rot      = self.rotacoes.get(idx_orig, 0)
            chave    = (idx_orig, rot, largura)

            try:
                    # Usa cache se disponível, senão renderiza
                if chave in self.cache_pil:
                    img = self.cache_pil[chave]
                else:
                    # Lock para acesso thread-safe ao documento fitz
                    with self._fitz_lock:
                        pagina = self.doc.load_page(idx_orig)
                        rect   = pagina.rect
                        escala = largura / rect.width
                        mat    = fitz.Matrix(escala, escala).prerotate(rot)
                        pix    = pagina.get_pixmap(matrix=mat, alpha=False)
                        samples = bytes(pix.samples)
                        pw, ph  = pix.width, pix.height
                    img = Image.frombytes("RGB", (pw, ph), samples)
                    self._cache_put(chave, img)
            except Exception:
                continue
            # Envia a imagem PIL diretamente — não depende do cache para exibição
            self._fila.put((pos, img))

        # Último worker a terminar envia sinal de fim
        with self._fitz_lock:
            self._workers_ativos -= 1
            if self._workers_ativos == 0:
                self._fila.put(None)

    def _processar_fila(self):
        processados = 0
        try:
            while True:
                item = self._fila.get_nowait()
                if item is None:
                    self.progress.pack_forget()
                    self._atualizar_info()
                    return
                pos, img_pil = item
                # img_pil vem diretamente do worker — sem risco de evicção de cache
                if img_pil is not None and pos in self.cards:
                    img_tk = ImageTk.PhotoImage(img_pil)
                    self.imagens_tk[pos] = img_tk
                    self.cards[pos].set_imagem(img_tk)
                self._render_prontos += 1
                self.progress['value'] = self._render_prontos
                processados += 1
                if processados >= 15:  # mais itens por ciclo = UI menos travada
                    break
        except queue.Empty:
            pass
        self.root.after(16, self._processar_fila)  # ~60fps de atualização

    def _reorganizar(self):
        if not self.doc or not self.ordem_paginas:
            return
        largura = self.largura_thumb.get()
        colunas = self._calcular_colunas()

        for pos, card in self.cards.items():
            linha = pos // colunas
            col   = pos % colunas
            card.grid(row=linha, column=col, padx=8, pady=8, sticky='n')

        for c in range(colunas):
            self.frame_grade.columnconfigure(c, weight=1)

        if self.imagens_tk:
            primeiro_pos = next(iter(self.imagens_tk))
            primeiro_idx = self.ordem_paginas[primeiro_pos]
            rot = self.rotacoes.get(primeiro_idx, 0)
            chave_atual = (primeiro_idx, rot, largura)
            if chave_atual not in self.cache_pil:
                self._iniciar_renderizacao()

    def _calcular_colunas(self):
        w = self.canvas.winfo_width()
        if w < 10:
            w = self.root.winfo_width() - 20
        espaco = self.largura_thumb.get() + 30
        return max(1, w // espaco)

    def _callbacks(self):
        return {
            'click':       self._clicar,
            'ctrl_click':  self._ctrl_clicar,
            'shift_click': self._shift_clicar,
            'right_click': self._menu_contexto,
            'drag_start':  self._drag_inicio,
            'drag_move':   self._drag_mover,
            'drag_end':    self._drag_fim,
        }

    # ── Seleção ───────────────────────────────────────────────────────────────
    def _clicar(self, pos):
        self.selecionadas = {pos}
        self.ultima_sel   = pos
        self._atualizar_selecao()

    def _ctrl_clicar(self, pos):
        if pos in self.selecionadas:
            self.selecionadas.discard(pos)
        else:
            self.selecionadas.add(pos)
            self.ultima_sel = pos
        self._atualizar_selecao()

    def _shift_clicar(self, pos):
        if self.ultima_sel is None:
            self.selecionadas = {pos}
        else:
            a, b = min(self.ultima_sel, pos), max(self.ultima_sel, pos)
            self.selecionadas = set(range(a, b + 1))
        self._atualizar_selecao()

    def selecionar_tudo(self):
        self.selecionadas = set(range(len(self.ordem_paginas)))
        self._atualizar_selecao()

    def inverter_selecao(self):
        todas = set(range(len(self.ordem_paginas)))
        self.selecionadas = todas - self.selecionadas
        self._atualizar_selecao()

    def _atualizar_selecao(self):
        for pos, card in self.cards.items():
            card.set_selecionada(pos in self.selecionadas)
        self._atualizar_info()

    def _atualizar_info(self):
        if not self.doc:
            self.lbl_info.config(text="Nenhum PDF aberto")
            return
        total = len(self.ordem_paginas)
        sel   = len(self.selecionadas)
        txt   = f"{total} página{'s' if total != 1 else ''}"
        if sel:
            txt += f"  •  {sel} selecionada{'s' if sel != 1 else ''}"
        self.lbl_info.config(text=txt)

    # ── Rotação ───────────────────────────────────────────────────────────────
    def girar(self, graus):
        if not self.selecionadas:
            messagebox.showinfo("Aviso", "Nenhuma página selecionada.")
            return
        if graus % 360 == 0 and graus != 0:
            # Rotação 360° = não faz nada visualmente, mas confirma
            messagebox.showinfo("Rotação 360°",
                f"{len(self.selecionadas)} página(s) girada(s) 360°\n"
                "(retornam à orientação original)")
            return

        largura = self.largura_thumb.get()
        for pos in self.selecionadas:
            idx_orig = self.ordem_paginas[pos]
            rot_nova = (self.rotacoes.get(idx_orig, 0) + graus) % 360
            self.rotacoes[idx_orig] = rot_nova

            chaves = [k for k in self.cache_pil if k[0] == idx_orig]
            for k in chaves:
                del self.cache_pil[k]

            chave = (idx_orig, rot_nova, largura)
            try:
                with self._fitz_lock:
                    pagina  = self.doc.load_page(idx_orig)
                    escala  = largura / pagina.rect.width
                    mat     = fitz.Matrix(escala, escala).prerotate(rot_nova)
                    pix     = pagina.get_pixmap(matrix=mat, alpha=False)
                    samples = bytes(pix.samples)
                    pw, ph  = pix.width, pix.height
                img = Image.frombytes("RGB", (pw, ph), samples)
                self._cache_put(chave, img)
                img_tk = ImageTk.PhotoImage(img)
                self.imagens_tk[pos] = img_tk
                if pos in self.cards:
                    self.cards[pos].set_imagem(img_tk)
                    self.cards[pos].set_rotacao_label(rot_nova)
            except Exception:
                pass

        qtd = len(self.selecionadas)
        self._set_status(
            f"Girado {graus:+}°  —  {qtd} página{'s' if qtd > 1 else ''}")

    # ── Excluir ───────────────────────────────────────────────────────────────
    def excluir(self):
        if not self.selecionadas:
            messagebox.showinfo("Aviso", "Nenhuma página selecionada.")
            return
        qtd = len(self.selecionadas)
        if not messagebox.askyesno("Confirmar",
                f"Excluir {qtd} página{'s' if qtd > 1 else ''}?\n"
                "Esta ação não pode ser desfeita nesta sessão."):
            return
        for pos in sorted(self.selecionadas, reverse=True):
            self.ordem_paginas.pop(pos)
        self.selecionadas.clear()
        self.ultima_sel = None
        self._set_status(f"{qtd} página(s) excluída(s)")
        self._iniciar_renderizacao()

    # ── Inserir PDF ───────────────────────────────────────────────────────────
    def inserir_pdf(self):
        if not self.doc:
            messagebox.showwarning("Aviso", "Abra um PDF primeiro.")
            return
        caminho = filedialog.askopenfilename(
            filetypes=[("Arquivos PDF", "*.pdf")],
            title="Selecionar PDF para Inserir")
        if not caminho:
            return
        pos_insercao = (min(self.selecionadas) + 1
                        if self.selecionadas else len(self.ordem_paginas))
        try:
            doc_ins    = fitz.open(caminho)
            qtd_novas  = len(doc_ins)
            idx_inicio = len(self.doc)
            self.doc.insert_pdf(doc_ins)
            doc_ins.close()
            novos = list(range(idx_inicio, idx_inicio + qtd_novas))
            for i, idx in enumerate(novos):
                self.ordem_paginas.insert(pos_insercao + i, idx)
            self._iniciar_renderizacao()
            self._set_status(
                f"{qtd_novas} página(s) inserida(s) na posição {pos_insercao + 1}")
            messagebox.showinfo("Sucesso",
                f"{qtd_novas} página(s) inserida(s) na posição {pos_insercao + 1}.")
        except Exception as ex:
            messagebox.showerror("Erro", f"Erro ao inserir PDF:\n{ex}")

    # ── Crop ─────────────────────────────────────────────────────────────────
    def _crop_selecionada(self):
        """Crop da primeira página selecionada (ou pede para selecionar)."""
        if not self.doc:
            messagebox.showwarning("Aviso", "Nenhum PDF aberto.")
            return
        if not self.selecionadas:
            messagebox.showinfo("Aviso", "Selecione uma página para recortar.")
            return
        pos = min(self.selecionadas)
        self.abrir_crop(pos)

    def abrir_crop(self, pos):
        idx_orig = self.ordem_paginas[pos]
        rot = self.rotacoes.get(idx_orig, 0)
        try:
            pagina = self.doc.load_page(idx_orig)
            rect   = pagina.rect
            escala = min(900 / rect.width, 850 / rect.height, 2.0)
            mat    = fitz.Matrix(escala, escala).prerotate(rot)
            pix    = pagina.get_pixmap(matrix=mat, alpha=False)
            img    = Image.open(io.BytesIO(pix.tobytes("png")))
        except Exception as ex:
            messagebox.showerror("Erro", f"Erro ao abrir crop:\n{ex}")
            return

        JanelaCrop(self.root, img, escala, idx_orig, pos,
                   self._aplicar_crop)

    def _aplicar_crop(self, idx_orig, pos, rect_fitz):
        """Callback da janela de crop."""
        if rect_fitz is None:
            self.crops.pop(idx_orig, None)
            self._set_status(f"Crop removido da página {pos + 1}")
        else:
            self.crops[idx_orig] = rect_fitz
            self._set_status(f"Crop aplicado à página {pos + 1}")
        self._invalidar_e_atualizar(idx_orig, pos)

    def _invalidar_e_atualizar(self, idx_orig, pos):
        chaves = [k for k in self.cache_pil if k[0] == idx_orig]
        for k in chaves:
            del self.cache_pil[k]
        largura = self.largura_thumb.get()
        rot     = self.rotacoes.get(idx_orig, 0)
        try:
            with self._fitz_lock:
                pagina  = self.doc.load_page(idx_orig)
                escala  = largura / pagina.rect.width
                mat     = fitz.Matrix(escala, escala).prerotate(rot)
                pix     = pagina.get_pixmap(matrix=mat, alpha=False)
                samples = bytes(pix.samples)
                pw, ph  = pix.width, pix.height
            img = Image.frombytes("RGB", (pw, ph), samples)
            if idx_orig in self.crops:
                cr  = self.crops[idx_orig]
                img = img.crop((int(cr.x0 * escala), int(cr.y0 * escala),
                                int(cr.x1 * escala), int(cr.y1 * escala)))
            chave = (idx_orig, rot, largura)
            self._cache_put(chave, img)
            img_tk = ImageTk.PhotoImage(img)
            self.imagens_tk[pos] = img_tk
            if pos in self.cards:
                self.cards[pos].set_imagem(img_tk)
        except Exception:
            pass

    # ── Menu de contexto ─────────────────────────────────────────────────────
    def _menu_contexto(self, pos, event):
        idx_orig = self.ordem_paginas[pos]
        rot_atual = self.rotacoes.get(idx_orig, 0)

        menu = tk.Menu(self.root, tearoff=0, bg='#1a1a2e', fg='#e0e0e0',
                       activebackground='#0e639c', activeforeground='white',
                       font=('Segoe UI', 9))
        menu.add_command(label=f"  📄  Página {pos + 1}  (rot. {rot_atual}°)",
                         state='disabled',
                         font=('Segoe UI', 9, 'bold'))
        menu.add_separator()

        sub_rot = tk.Menu(menu, tearoff=0, bg='#1a1a2e', fg='#e0e0e0',
                          activebackground='#0e639c', activeforeground='white',
                          font=('Segoe UI', 9))
        sub_rot.add_command(label="  ⟲  90° à Esquerda",
                            command=lambda: self._girar_uma(pos, -90))
        sub_rot.add_command(label="  ⟳  90° à Direita",
                            command=lambda: self._girar_uma(pos, 90))
        sub_rot.add_command(label="  ↺  180°",
                            command=lambda: self._girar_uma(pos, 180))
        sub_rot.add_command(label="  🔄  360° (sem mudança visual)",
                            command=lambda: self._girar_uma(pos, 360))
        menu.add_cascade(label="  ⟳  Rotacionar", menu=sub_rot)

        menu.add_command(label="  ✂  Recortar (Crop)",
                         command=lambda: self.abrir_crop(pos))
        menu.add_separator()
        menu.add_command(label="  🗑  Excluir esta página",
                         command=lambda: self._excluir_uma(pos))
        menu.tk_popup(event.x_root, event.y_root)

    def _girar_uma(self, pos, graus):
        ante = self.selecionadas.copy()
        self.selecionadas = {pos}
        self.girar(graus)
        self.selecionadas = ante
        self._atualizar_selecao()

    def _excluir_uma(self, pos):
        if messagebox.askyesno("Confirmar", f"Excluir a página {pos + 1}?"):
            self.ordem_paginas.pop(pos)
            self.selecionadas.discard(pos)
            self._iniciar_renderizacao()

    # ── Drag & Drop (reordenação) ─────────────────────────────────────────────
    def _drag_inicio(self, pos, event):
        self._drag_origem = pos
        if pos not in self.selecionadas:
            self.selecionadas = {pos}
            self._atualizar_selecao()
        if pos in self.imagens_tk:
            self._fantasma = tk.Toplevel(self.root)
            self._fantasma.overrideredirect(True)
            self._fantasma.attributes('-alpha', 0.65)
            self._fantasma.attributes('-topmost', True)
            tk.Label(self._fantasma, image=self.imagens_tk[pos],
                     bg='#0e639c').pack()
            self._fantasma.geometry(f"+{event.x_root-40}+{event.y_root-60}")

    def _drag_mover(self, pos, event):
        if self._fantasma:
            self._fantasma.geometry(f"+{event.x_root-40}+{event.y_root-60}")

    def _drag_fim(self, pos, event):
        if self._fantasma:
            self._fantasma.destroy()
            self._fantasma = None
        if self._drag_origem is None:
            return
        destino = self._pos_drop(event)
        if destino is not None and destino != self._drag_origem:
            idx = self.ordem_paginas.pop(self._drag_origem)
            d   = destino if destino < self._drag_origem else destino
            d   = max(0, min(d, len(self.ordem_paginas)))
            self.ordem_paginas.insert(d, idx)
            self.selecionadas = {d}
            self._iniciar_renderizacao()
        self._drag_origem = None

    def _pos_drop(self, event):
        xr, yr = event.x_root, event.y_root
        for pos, card in self.cards.items():
            try:
                cx, cy = card.winfo_rootx(), card.winfo_rooty()
                cw, ch = card.winfo_width(), card.winfo_height()
                if cx <= xr <= cx + cw and cy <= yr <= cy + ch:
                    return pos
            except Exception:
                pass
        return None


# ── Ponto de entrada ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = PDFEditorApp(root)
    root.mainloop()