import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import csv
import time
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class BiomechanicalTestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Evaluación Biomecánica - Pruebas de Columna")
        self.root.geometry("1050x750")
        
        # Variables de control y comunicación
        self.serial_port = None
        self.is_reading = False
        
        # Variables de datos
        self.data_time = []
        self.data_force = []
        self.data_deformation = []
        self.start_time = 0
        
        # Variables para calibración (Tara/Cero)
        self.latest_raw_force = 0.0
        self.latest_raw_def = 0.0
        self.offset_force = 0.0
        self.offset_deformation = 0.0
        
        self.valve_mode = tk.StringVar(value="MAIN") # Modos: MAIN, SEC, BOTH
        
        self.setup_main_window()
        self.connect_serial()

    def setup_main_window(self):
        # Panel de Configuración
        config_frame = ttk.LabelFrame(self.root, text="Configuración de la Prueba")
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Label(config_frame, text="Frecuencia (1-5 Hz):").grid(row=0, column=0, padx=5, pady=5)
        self.entry_freq = ttk.Entry(config_frame, width=10)
        self.entry_freq.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(config_frame, text="Presión de Regulación (MPa):").grid(row=0, column=2, padx=5, pady=5)
        self.entry_pressure = ttk.Entry(config_frame, width=10)
        self.entry_pressure.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(config_frame, text="Número de Ciclos:").grid(row=0, column=4, padx=5, pady=5)
        self.entry_cycles = ttk.Entry(config_frame, width=10)
        self.entry_cycles.grid(row=0, column=5, padx=5, pady=5)

        mode_frame = ttk.LabelFrame(self.root, text="Modo de Operación de Válvulas")
        mode_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        self.use_main = tk.BooleanVar(value=True)
        self.use_sec = tk.BooleanVar(value=True)

        cb_main = ttk.Checkbutton(mode_frame, text="Usar Principal (Compresión/Retorno Rápido)", variable=self.use_main, command=self.validate_modes)
        cb_main.pack(side=tk.LEFT, padx=20)
        
        cb_sec = ttk.Checkbutton(mode_frame, text="Usar Secundarias (Retorno Lento / Despresurización)", variable=self.use_sec, command=self.validate_modes)
        cb_sec.pack(side=tk.LEFT, padx=20)

        # Botones de Control Principal
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        self.btn_start = ttk.Button(btn_frame, text="Iniciar Prueba", command=self.start_test)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        
        self.btn_stop = ttk.Button(btn_frame, text="Detener Prueba", command=self.stop_test, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        
        # Botón de Emergencia (Rojo)
        style = ttk.Style()
        style.configure("Emergency.TButton", foreground="red", font=('Arial', 10, 'bold'))
        self.btn_emergency = ttk.Button(btn_frame, text="PARADA DE EMERGENCIA", style="Emergency.TButton", command=self.emergency_stop)
        self.btn_emergency.pack(side=tk.LEFT, padx=20)
        
        self.btn_export = ttk.Button(btn_frame, text="Exportar CSV", command=self.export_csv, state=tk.DISABLED)
        self.btn_export.pack(side=tk.RIGHT, padx=5)

        self.btn_calib = ttk.Button(btn_frame, text="Abrir Calibración", command=self.open_calibration_window)
        self.btn_calib.pack(side=tk.RIGHT, padx=5)

        self.btn_sim = ttk.Button(btn_frame, text="Simulador de Flujo", command=self.open_simulation_window)
        self.btn_sim.pack(side=tk.RIGHT, padx=5)

        # Configuración de la Gráfica (Fuerza vs Deformación)
        self.fig, self.ax = plt.subplots(figsize=(8, 5))
        self.ax.set_title("Esfuerzo vs Deformación (Nube de Puntos)")
        self.ax.set_xlabel("Deformación (mm)")
        self.ax.set_ylabel("Fuerza (N)")
        self.ax.grid(True)
        self.scatter_plot = self.ax.scatter([], [], c='b', alpha=0.5)
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

    def validate_modes(self):
        # Asegurar que al menos una válvula quede activa para que la física funcione
        if not self.use_main.get() and not self.use_sec.get():
            messagebox.showwarning("Modo Inválido", "Debe estar activa al menos una configuración de válvulas (Principal o Secundaria).")
            self.use_main.set(True)

    def connect_serial(self):
        ports = serial.tools.list_ports.comports()
        esp_port = ports[0].device if ports else None 
        
        try:
            if esp_port:
                self.serial_port = serial.Serial(esp_port, 9600, timeout=0.01)
                print(f"Conectado a {esp_port} a 9600 baudios.")
                # Iniciar hilo de lectura permanente para capturar datos incluso en calibración
                self.is_reading = True
                threading.Thread(target=self.read_serial_data, daemon=True).start()
                self.update_plot()
            else:
                messagebox.showwarning("Advertencia", "No se detectó el ESP32.")
        except Exception as e:
            messagebox.showerror("Error Serial", f"No se pudo conectar: {str(e)}")

    def open_calibration_window(self):
        calib_win = tk.Toplevel(self.root)
        calib_win.title("Calibración y Control Manual")
        calib_win.geometry("400x450")
        
        ttk.Label(calib_win, text="Control de Válvula Principal (3 Posiciones)", font=('Arial', 10, 'bold')).pack(pady=5)
        
        ttk.Button(calib_win, text="Principal -> Ramal A (Compresión)", 
                   command=lambda: self.send_serial_command("CMD_MAIN_A")).pack(pady=2, fill=tk.X, padx=20)
        ttk.Button(calib_win, text="Principal -> Ramal B (Retracción rápida)", 
                   command=lambda: self.send_serial_command("CMD_MAIN_B")).pack(pady=2, fill=tk.X, padx=20)
        ttk.Button(calib_win, text="Principal -> Tanque (Centro)", 
                   command=lambda: self.send_serial_command("CMD_MAIN_T")).pack(pady=2, fill=tk.X, padx=20)
        
        ttk.Label(calib_win, text="Control de Válvulas Secundarias", font=('Arial', 10, 'bold')).pack(pady=5)
        
        ttk.Button(calib_win, text="Secundaria A -> Desvío a Tanque", 
                   command=lambda: self.send_serial_command("CMD_SEC_A_TANK")).pack(pady=2, fill=tk.X, padx=20)
        ttk.Button(calib_win, text="Secundaria B -> Desvío a Tanque", 
                   command=lambda: self.send_serial_command("CMD_SEC_B_TANK")).pack(pady=2, fill=tk.X, padx=20)
        
        ttk.Button(calib_win, text="Detener Todo (Centro y Tanque)", 
                   command=lambda: self.send_serial_command("CMD_STOP_ALL")).pack(pady=10, fill=tk.X, padx=20)

        ttk.Separator(calib_win, orient='horizontal').pack(fill='x', pady=5)
        ttk.Label(calib_win, text="Calibración de Sensores (Cero)", font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Botones de Cero (Tara)
        frame_ceros = ttk.Frame(calib_win)
        frame_ceros.pack(fill=tk.X, padx=20)
        ttk.Button(frame_ceros, text="Fijar Cero Fuerza", command=self.set_zero_force).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(frame_ceros, text="Fijar Cero Deformación", command=self.set_zero_deformation).pack(side=tk.RIGHT, expand=True, padx=5)

    def set_zero_force(self):
        self.offset_force = self.latest_raw_force
        print(f"Cero de fuerza fijado. Offset: {self.offset_force}")

    def set_zero_deformation(self):
        self.offset_deformation = self.latest_raw_def
        print(f"Cero de deformación fijado. Offset: {self.offset_deformation}")

    def open_simulation_window(self):
        self.sim_win = tk.Toplevel(self.root)
        self.sim_win.title("Simulador Dinámico de Válvulas y Pistón")
        self.sim_win.geometry("700x650")
        
        # Estados: main: 'T', 'A', 'B' | sec_a: 'PASS', 'TANK' | sec_b: 'PASS', 'TANK'
        self.sim_state = {"main": "T", "sec_a": "PASS", "sec_b": "PASS"}
        self.piston_pos = 0.0 # 0 = arriba (retraído), 80 = abajo (comprimido)
        
        ttk.Label(self.sim_win, text="Simulador Físico de Flujo y Retorno", font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.sim_canvas = tk.Canvas(self.sim_win, width=550, height=450, bg="white", relief=tk.SUNKEN, bd=2)
        self.sim_canvas.pack(pady=10)
        
        controls_frame = ttk.Frame(self.sim_win)
        controls_frame.pack(fill=tk.X, padx=20)
        
        ttk.Button(controls_frame, text="Principal: Compresión (A)", command=lambda: self.set_sim_state("main", "A")).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(controls_frame, text="Principal: Retracción (B)", command=lambda: self.set_sim_state("main", "B")).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(controls_frame, text="Principal: Centro (T)", command=lambda: self.set_sim_state("main", "T")).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Button(controls_frame, text="Sec A: Conectar/Tanque", command=lambda: self.toggle_sec_sim("sec_a")).grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(controls_frame, text="Sec B: Conectar/Tanque", command=lambda: self.toggle_sec_sim("sec_b")).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(controls_frame, text="Reset Simulador", command=lambda: self.reset_sim()).grid(row=1, column=2, padx=5, pady=5)
        
        style = ttk.Style()
        style.configure("Exec.TButton", font=('Arial', 10, 'bold'), foreground="blue")
        ttk.Button(self.sim_win, text="ENVIAR ESTADOS SIMULADOS AL ESP32", command=self.execute_sim_state, style="Exec.TButton").pack(pady=10)
        
        self.sim_update_loop()

    def set_sim_state(self, valve, state):
        self.sim_state[valve] = state

    def toggle_sec_sim(self, valve):
        self.sim_state[valve] = "TANK" if self.sim_state[valve] == "PASS" else "PASS"

    def reset_sim(self):
        self.sim_state = {"main": "T", "sec_a": "PASS", "sec_b": "PASS"}
        self.piston_pos = 0.0

    def sim_update_loop(self):
        if not hasattr(self, 'sim_win') or not self.sim_win.winfo_exists():
            return

        delta = 0.0
        # Análisis del comportamiento físico del retorno
        if self.sim_state["main"] == "A":
            if self.sim_state["sec_a"] == "PASS":
                delta = 3.0  # Compresión empujando la vértebra
            else:
                delta = 0.0  # Flujo se desvía directo al tanque por la T, presión nula
        elif self.sim_state["main"] == "B":
            if self.sim_state["sec_b"] == "PASS":
                delta = -6.0 # Retracción forzada (muy rápida)
        elif self.sim_state["main"] == "T":
            if self.sim_state["sec_a"] == "TANK":
                delta = -0.5 # Retorno lento: despresurización, la muestra empuja de vuelta

        self.piston_pos += delta
        if self.piston_pos > 80.0: self.piston_pos = 80.0
        if self.piston_pos < 0.0: self.piston_pos = 0.0
        
        self.draw_simulation()
        self.sim_win.after(50, self.sim_update_loop)

    def draw_simulation(self):
        self.sim_canvas.delete("all")
        
        flow_a = self.sim_state["main"] == "A"
        flow_b = self.sim_state["main"] == "B"
        
        # Colores dinámicos
        c_a_main = "red" if flow_a else "lightgray"
        c_a_pist = "red" if flow_a and self.sim_state["sec_a"] == "PASS" else "lightgray"
        c_a_sec = "red" if flow_a else "lightgray"
        c_a_tank = "orange" if self.sim_state["sec_a"] == "TANK" and (flow_a or self.piston_pos > 0) else "lightgray"
        
        c_b_main = "blue" if flow_b else "lightgray"
        c_b_pist = "blue" if flow_b and self.sim_state["sec_b"] == "PASS" else "lightgray"
        c_b_sec = "blue" if flow_b else "lightgray"
        c_b_tank = "orange" if self.sim_state["sec_b"] == "TANK" and flow_b else "lightgray"

        # 1. Bomba
        self.sim_canvas.create_rectangle(225, 380, 325, 420, fill="#555555")
        self.sim_canvas.create_text(275, 400, text="BOMBA / TANQUE", fill="white", font=('Arial', 9, 'bold'))
        
        # 2. Válvula Principal (3 Posiciones)
        self.sim_canvas.create_rectangle(210, 310, 340, 350, fill="white", outline="black", width=2)
        self.sim_canvas.create_text(275, 330, text=f"PRINCIPAL [{self.sim_state['main']}]", font=('Arial', 9, 'bold'))
        self.sim_canvas.create_line(275, 380, 275, 350, width=6, fill="red" if flow_a or flow_b else "lightgray")
        
        # 3. Ramal A (Compresión) y T-Junction
        self.sim_canvas.create_line(240, 310, 240, 240, width=6, fill=c_a_main)
        self.sim_canvas.create_line(240, 240, 240, 20, width=6, fill=c_a_pist)
        self.sim_canvas.create_line(240, 20, 275, 20, width=6, fill=c_a_pist, arrow=tk.LAST)
        
        self.sim_canvas.create_line(240, 240, 150, 240, width=6, fill=c_a_sec)
        self.sim_canvas.create_rectangle(100, 220, 150, 260, fill="white", outline="red", width=2)
        self.sim_canvas.create_text(125, 240, text=f"SEC A\n[{self.sim_state['sec_a']}]", font=('Arial', 8, 'bold'))
        self.sim_canvas.create_line(125, 260, 125, 400, width=6, fill=c_a_tank, arrow=tk.LAST)
        self.sim_canvas.create_text(100, 380, text="A Tanque", font=('Arial', 8))

        # 4. Ramal B (Retracción) y T-Junction
        self.sim_canvas.create_line(310, 310, 310, 240, width=6, fill=c_b_main)
        self.sim_canvas.create_line(310, 240, 310, 120, width=6, fill=c_b_pist)
        self.sim_canvas.create_line(310, 120, 275, 120, width=6, fill=c_b_pist, arrow=tk.LAST)
        
        self.sim_canvas.create_line(310, 240, 400, 240, width=6, fill=c_b_sec)
        self.sim_canvas.create_rectangle(400, 220, 450, 260, fill="white", outline="blue", width=2)
        self.sim_canvas.create_text(425, 240, text=f"SEC B\n[{self.sim_state['sec_b']}]", font=('Arial', 8, 'bold'))
        self.sim_canvas.create_line(425, 260, 425, 400, width=6, fill=c_b_tank, arrow=tk.LAST)
        self.sim_canvas.create_text(450, 380, text="A Tanque", font=('Arial', 8))

        # 5. Actuador (Cilindro) y Vértebra Bovína
        self.sim_canvas.create_rectangle(250, 20, 300, 120, outline="black", width=2)
        p_y = 20 + self.piston_pos
        self.sim_canvas.create_rectangle(250, p_y, 300, p_y + 15, fill="gray") # Pistón
        self.sim_canvas.create_rectangle(270, p_y + 15, 280, 170, fill="silver") # Vástago
        
        self.sim_canvas.create_oval(240, 170, 310, 200, fill="bisque", outline="saddlebrown")
        self.sim_canvas.create_text(275, 185, text="Vértebra", font=('Arial', 8))

    def execute_sim_state(self):
        cmd_main = f"CMD_MAIN_{self.sim_state['main']}"
        cmd_seca = f"CMD_SEC_A_{self.sim_state['sec_a']}"
        cmd_secb = f"CMD_SEC_B_{self.sim_state['sec_b']}"
        
        self.send_serial_command(cmd_main)
        self.send_serial_command(cmd_seca)
        self.send_serial_command(cmd_secb)
                
        messagebox.showinfo("Comandos Enviados", f"Se configuró el circuito hidráulico:\nPrincipal: {self.sim_state['main']}\nSec A: {self.sim_state['sec_a']}\nSec B: {self.sim_state['sec_b']}")

    def send_serial_command(self, command):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.write(f"{command}\n".encode('utf-8'))
            print(f"Comando enviado: {command}")
        else:
            print("Puerto serie no disponible.")

    def start_test(self):
        try:
            freq = float(self.entry_freq.get())
            pressure = float(self.entry_pressure.get())
            cycles = int(self.entry_cycles.get())
            mode_main = 1 if self.use_main.get() else 0
            mode_sec = 1 if self.use_sec.get() else 0
            
            if not (1 <= freq <= 5):
                raise ValueError("La frecuencia debe estar entre 1 y 5 Hz.")
                
            self.data_time.clear()
            self.data_force.clear()
            self.data_deformation.clear()
            self.ax.clear()
            self.ax.set_title("Esfuerzo vs Deformación")
            self.ax.set_xlabel("Deformación (mm)")
            self.ax.set_ylabel("Fuerza (N)")
            self.ax.grid(True)
            
            cmd = f"START,{freq},{pressure},{cycles},{mode_main},{mode_sec}"
            self.send_serial_command(cmd)
            
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.btn_export.config(state=tk.DISABLED)
            self.btn_calib.config(state=tk.DISABLED)
            
            self.start_time = time.time()
            
        except ValueError as e:
            messagebox.showerror("Error de Entrada", str(e))

    def stop_test(self):
        self.send_serial_command("CMD_STOP_TEST")
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_calib.config(state=tk.NORMAL)
        self.btn_export.config(state=tk.NORMAL)
        print("Prueba detenida normalmente.")

    def emergency_stop(self):
        # Comando para apagar válvula principal y forzar el actuador a retroceder rápidamente (Posición B) + Alivio
        self.send_serial_command("CMD_EMERGENCY_RETRACT")
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_calib.config(state=tk.NORMAL)
        self.btn_export.config(state=tk.NORMAL)
        messagebox.showwarning("PARADA DE EMERGENCIA", "¡Retracción rápida forzada! Válvula principal activada en reversa (Ramal B) para liberar la presión inmediatamente.")

    def read_serial_data(self):
        while self.is_reading and self.serial_port and self.serial_port.is_open:
            try:
                line = self.serial_port.readline().decode('utf-8').strip()
                if line and not line.startswith("CMD") and not line.startswith("START"):
                    parts = line.split(',')
                    if len(parts) == 2:
                        self.latest_raw_force = float(parts[0])
                        self.latest_raw_def = float(parts[1])
                        
                        # Aplicar los offsets de calibración
                        calibrated_force = self.latest_raw_force - self.offset_force
                        calibrated_def = self.latest_raw_def - self.offset_deformation
                        
                        # Si la prueba está activa (btn_stop habilitado), guardar los datos
                        if str(self.btn_stop['state']) == tk.NORMAL:
                            current_time = time.time() - self.start_time
                            self.data_time.append(current_time)
                            self.data_force.append(calibrated_force)
                            self.data_deformation.append(calibrated_def)
            except Exception:
                pass
            time.sleep(0.005) # Para lograr lectura a >100Hz

    def update_plot(self):
        # Solo actualizar gráfica si la prueba está corriendo
        if str(self.btn_stop['state']) == tk.NORMAL:
            if len(self.data_force) > 0 and len(self.data_deformation) > 0:
                self.ax.clear()
                self.ax.set_title("Esfuerzo vs Deformación (Nube de Puntos)")
                self.ax.set_xlabel("Deformación (mm)")
                self.ax.set_ylabel("Fuerza (N)")
                self.ax.grid(True)
                
                self.ax.scatter(self.data_deformation, self.data_force, c='b', s=10, alpha=0.5)
                self.canvas.draw()
        
        # Refresco a 100Hz (10 ms)
        self.root.after(10, self.update_plot)

    def export_csv(self):
        if not self.data_force:
            messagebox.showinfo("Sin Datos", "No hay datos registrados para exportar.")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Exportar Registro Biomecánico"
        )
        
        if file_path:
            try:
                with open(file_path, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['Tiempo (s)', 'Deformacion (mm)', 'Fuerza (N)'])
                    for i in range(len(self.data_force)):
                        writer.writerow([round(self.data_time[i], 3), round(self.data_deformation[i], 3), round(self.data_force[i], 3)])
                messagebox.showinfo("Exportación Exitosa", f"Datos guardados en:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error al Exportar", f"No se pudo guardar el archivo: {e}")

    def on_closing(self):
        self.is_reading = False
        if self.serial_port and self.serial_port.is_open:
            self.send_serial_command("CMD_EMERGENCY") # Apagar todo por seguridad al salir
            self.serial_port.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = BiomechanicalTestApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
