import streamlit as st
from streamlit_option_menu import option_menu
import mysql.connector
import datetime
import sqlite3
import pandas as pd
import io
import altair as alt
import xlsxwriter
import hashlib
import os
import base64


def get_connection():
    return mysql.connector.connect(
        host=st.secrets["DB_HOST"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        database=st.secrets["DB_NAME"],
        port=int(st.secrets["DB_PORT"])
    )



# =======================
# Fungsi Utilitas
# =======================
def hash_password(password):
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return base64.b64encode(salt + key).decode('utf-8')


def verify_password(password, hashed):
    hashed_bytes = base64.b64decode(hashed.encode('utf-8'))
    salt = hashed_bytes[:16]
    key = hashed_bytes[16:]
    new_key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return new_key == key


def user_exists(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None

def register_user(username, password):
    if user_exists(username):
        return False, "Username sudah digunakan."
    hashed = hash_password(password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", 
                   (username, hashed))
    conn.commit()
    cursor.close()
    conn.close()
    return True, "Registrasi berhasil."

def login_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result and verify_password(password, result[0]):
        return True
    return False




def simpan_hasil_ujian(nama, nim, matkul, skor):
    try:
        # Cek apakah skor valid
        if not isinstance(skor, (int, float)):
            st.error("Skor harus berupa angka!")
            return False

        # Koneksi ke database
        conn = get_connection()
        cursor = conn.cursor()

        # Query untuk menyimpan hasil ujian tanpa memasukkan ID (auto-increment)
        query = """
            INSERT INTO hasil_ujian (nama, nim, matkul, skor, waktu)
            VALUES (%s, %s, %s, %s, NOW())
        """
        cursor.execute(query, (nama, nim, matkul, skor))

        # Commit dan tutup koneksi
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Terjadi error saat menyimpan hasil ujian: {e}")
        return False


def form_identitas():
    st.subheader("🧾 Form Identitas Mahasiswa")

    nama = st.text_input("Nama Lengkap")
    nim = st.text_input("NIM")
    kelas = st.text_input("Kelas")
    matkul = st.selectbox("Mata Kuliah", ["Matematika", "Pemrograman", "Jaringan", "AI"])

    if st.button("Simpan Identitas"):
        if not nama or not nim or not kelas or not matkul:
            st.warning("Mohon lengkapi semua data.")
            return

        st.session_state["data_identitas"] = {
            "nama": nama,
            "nim": nim,
            "kelas": kelas,
            "matkul": matkul
        }
        st.session_state["form_filled"] = True
        st.success("✅ Identitas berhasil disimpan.")
        st.rerun()

def halaman_hasil_ujian():
    st.title("🏆 Peringkat 10 Teratas")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nama, nim, matkul, skor, waktu FROM hasil_ujian ORDER BY skor DESC, waktu ASC LIMIT 10")
    data = cursor.fetchall()
    conn.close()

    if not data:
        st.info("Belum ada data hasil ujian.")
        return

    df = pd.DataFrame(data, columns=["Nama", "NIM", "Mata Kuliah", "Skor", "Waktu"])
    st.dataframe(df)


# =======================
# Halaman Soal Ujian
# =======================
# "box-arrow-right"
def soal_ujian_page_user():
    with st.sidebar:
        selected = option_menu("📑 Navigasi", ["Ujian", "Hasil Ujian"],
                               icons=["file-earmark-text", "clipboard-data"],
                               menu_icon="cast", default_index=0)

    col1, col2 = st.columns([1, 4])  # Navigasi di kiri, konten di kanan

    with col2:
        if selected == "Ujian":
            halaman_ujian()
        elif selected == "Hasil Ujian":
            halaman_hasil_ujian()
        elif selected == "Logout":
            st.session_state.clear()
            st.success("Anda telah logout.")
            st.rerun()
            
def sudah_mengerjakan_ujian(nim, matkul):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM hasil_ujian WHERE nim=%s AND matkul=%s"
    cursor.execute(query, (nim, matkul))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count > 0

def halaman_ujian():
    st.title("📘 Halaman Ujian Mahasiswa")

    if "form_filled" not in st.session_state or not st.session_state["form_filled"]:
        form_identitas()
        return

    data = st.session_state["data_identitas"]
    st.success(f"Selamat datang, {data['nama']} ({data['nim']})")
    st.write(f"📚 Mata Kuliah: {data['matkul']} | Kelas: {data['kelas']}")

    if "ujian_dimulai" not in st.session_state:
        st.session_state["ujian_dimulai"] = False
    if "start_time" not in st.session_state:
        st.session_state["start_time"] = None
    if "jawaban_user" not in st.session_state:
        st.session_state["jawaban_user"] = []

    total_menit = 5
    total_detik = total_menit * 60

    if not st.session_state["ujian_dimulai"]:
        if sudah_mengerjakan_ujian(data["nim"], data["matkul"]):
            st.warning("⚠️ Anda sudah mengerjakan ujian untuk mata kuliah ini. Anda tidak dapat mengulang kembali.")
            return
        
        if st.button("▶️ Mulai Ujian"):
            st.session_state["ujian_dimulai"] = True
            st.session_state["start_time"] = datetime.datetime.now()
            st.rerun()
    else:
        waktu_sekarang = datetime.datetime.now()
        durasi = waktu_sekarang - st.session_state["start_time"]
        sisa_waktu = total_detik - durasi.total_seconds()

        if sisa_waktu <= 0:
            st.error("⏰ Waktu ujian habis!")
            st.session_state["ujian_dimulai"] = False
            return

        st.warning(f"⏳ Sisa waktu: {str(datetime.timedelta(seconds=int(sisa_waktu)))}")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, pertanyaan, opsi_1, opsi_2, opsi_3, opsi_4, jawaban FROM soal_ujian WHERE matkul = %s", (data["matkul"],))
        soal_data = cursor.fetchall()
        conn.close()

        if not soal_data:
            st.error("⚠️ Belum ada soal untuk mata kuliah ini. Silakan hubungi admin.")
            return

        st.markdown("### 🧪 Soal Pilihan Ganda")

        if len(st.session_state["jawaban_user"]) != len(soal_data):
            st.session_state["jawaban_user"] = [None] * len(soal_data)

        for i, soal in enumerate(soal_data):
            st.markdown(f"**{i+1}. {soal[1]}**")
            pilihan = {"A": soal[2], "B": soal[3], "C": soal[4], "D": soal[5]}
            opsi = st.radio(
                f"Jawaban Anda untuk Soal {i+1}",
                options=["A", "B", "C", "D"],
                format_func=lambda x: f"{x}. {pilihan[x]}",
                key=f"soal_{i}"
            )
            st.session_state["jawaban_user"][i] = opsi

        # Cek apakah ujian sudah pernah disubmit
        if sudah_mengerjakan_ujian(data["nim"], data["matkul"]):
            st.warning("⚠️ Anda sudah mengirim jawaban untuk ujian ini. Anda tidak bisa mengirimkan jawaban lagi.")
        else:
            if st.button("Kirim Jawaban"):
                benar = 0
                total = len(soal_data)
                hasil = []
                skor_per_soal = 100 / total
                skor_total = 0

                for i in range(total):
                    soal_text = soal_data[i][2]
                    pilihan = soal_data[i][3:7]
                    correct = soal_data[i][6]
                    user_ans = st.session_state["jawaban_user"][i]

                    if user_ans == correct:
                        benar += 1
                        skor_total += skor_per_soal
                        hasil.append(f"**Soal {i+1}**: ✅ Benar\n- Jawaban Anda: **{user_ans}**\n- Kunci Jawaban: **{correct}**")
                    else:
                        hasil.append(f"**Soal {i+1}**: ❌ Salah\n- Jawaban Anda: **{user_ans}**\n- Kunci Jawaban: **{correct}**")

                st.markdown("---")
                st.subheader("📊 Rekap Jawaban Ujian")

                for item in hasil:
                    st.markdown(item)
                    st.markdown("---")

                skor = skor_total
                st.success(f"🎯 Skor Akhir Anda: **{skor:.2f} / 100**")
                
                if simpan_hasil_ujian(data['nama'], data['nim'], data['matkul'], skor):
                    st.info("📥 Hasil ujian berhasil disimpan ke database.")
                else:
                    st.error("❌ Gagal menyimpan hasil ujian.")

                if skor == 100:
                    st.balloons()
                                    
                
def admin_dashboard():
    with st.sidebar:
        selected = option_menu("📂 Navigasi Admin", [
            "Statistik & Data Hasil Ujian",
            "Statistik Nilai",
            "Top 10 Skor Tertinggi",
            "Export Data ke Excel",
            "Upload Soal Ujian"
        ],
        icons=['bar-chart-line', 'clipboard-data', 'trophy', 'file-earmark-excel', 'cloud-upload'],
        menu_icon="cast", default_index=0)

    col1, col2 = st.columns([1, 3])  # Sidebar (kiri) kecil, konten (kanan) besar

    with col2:
        if selected == "Statistik & Data Hasil Ujian":
            tampilkan_data_hasil_ujian()
        elif selected == "Statistik Nilai":
            tampilkan_statistik_nilai()
        elif selected == "Top 10 Skor Tertinggi":
            tampilkan_top_10()
        elif selected == "Export Data ke Excel":
            export_data_excel()
        elif selected == "Upload Soal Ujian":
            upload_soal_ujian()
            kelola_hasil_ujian()




def ambil_data_ujian():
    conn = get_connection()  # Koneksi aman
    cursor = conn.cursor()
    cursor.execute("SELECT id, nama, nim, matkul, skor, waktu FROM hasil_ujian ORDER BY waktu DESC")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Ubah ke DataFrame
    df = pd.DataFrame(data, columns=["ID", "Nama", "NIM", "Mata Kuliah", "Skor", "Waktu"])
    return df


def tampilkan_data_hasil_ujian():
    st.title("📊 Statistik & Data Hasil Ujian")
    df = ambil_data_ujian()
    if df.empty:
        st.info("Belum ada data hasil ujian.")
        return
    st.dataframe(df)

def tampilkan_statistik_nilai():
    st.title("📈 Statistik Nilai")
    df = ambil_data_ujian()
    if df.empty:
        st.info("Belum ada data.")
        return

    matkul_list = df["Mata Kuliah"].unique().tolist()
    selected_matkul = st.selectbox("📚 Pilih Mata Kuliah", ["Semua"] + matkul_list)

    if selected_matkul != "Semua":
        df = df[df["Mata Kuliah"] == selected_matkul]

    stats = df.groupby("Mata Kuliah")["Skor"].mean().reset_index()
    stats.rename(columns={"Skor": "Rata_Rata"}, inplace=True)

    chart = alt.Chart(stats).mark_bar(color="steelblue").encode(
        x=alt.X('Mata Kuliah:N', sort='-y', title=''),
        y=alt.Y('Rata_Rata:Q', title='Rata-Rata Skor'),
        tooltip=['Mata Kuliah', 'Rata_Rata']
    ).properties(
        width=600,
        height=400,
        title='📊 Rata-Rata Skor per Mata Kuliah'
    )
    st.altair_chart(chart, use_container_width=True)
    
def tampilkan_top_10():
    st.title("🏆 Top 10 Skor Tertinggi")
    df = ambil_data_ujian()
    if df.empty:
        st.info("Belum ada data.")
        return

    top_scores = df.sort_values(by="Skor", ascending=False).head(10)
    st.dataframe(top_scores[["Nama", "NIM", "Mata Kuliah", "Skor", "Waktu"]])
    
def export_data_excel():
    st.title("📁 Export Data ke Excel")
    df = ambil_data_ujian()
    if df.empty:
        st.info("Belum ada data.")
        return

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Hasil_Ujian')
        worksheet = writer.sheets['Hasil_Ujian']
        for i, column in enumerate(df.columns):
            column_width = max(df[column].astype(str).map(len).max(), len(column)) + 2
            worksheet.set_column(i, i, column_width)
    buffer.seek(0)

    st.download_button(
        label="📤 Download Excel",
        data=buffer,
        file_name='hasil_ujian.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    
def upload_soal_ujian():
    st.title("📤 Upload Soal Ujian")

    metode = st.radio("Pilih metode input soal:", ["🔼 Upload dari File Excel", "✍️ Input Manual"])

    if metode == "🔼 Upload dari File Excel":
        st.markdown("""
        ✅ Format Excel harus memiliki kolom:
        `matkul`, `pertanyaan`, `opsi_1`, `opsi_2`, `opsi_3`, `opsi_4`, `jawaban`  
        Kolom `id` tidak diperlukan dan akan dibuat otomatis oleh database.
        """)

        uploaded_file = st.file_uploader("Unggah File Excel", type=["xlsx"])

        if uploaded_file is not None:
            try:
                df = pd.read_excel(uploaded_file)

                required_columns = {"matkul", "pertanyaan", "opsi_1", "opsi_2", "opsi_3", "opsi_4", "jawaban"}
                if not required_columns.issubset(df.columns):
                    st.error(f"❌ Kolom tidak sesuai. Wajib ada: {', '.join(required_columns)}")
                    return

                st.dataframe(df)

                if st.button("✅ Simpan ke Database"):
                    try:
                        conn = get_connection()
                        c = conn.cursor()

                        inserted_count = 0
                        for _, row in df.iterrows():
                            c.execute("""
                                INSERT INTO soal_ujian (matkul, pertanyaan, opsi_1, opsi_2, opsi_3, opsi_4, jawaban)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (
                                row['matkul'],
                                row['pertanyaan'],
                                row['opsi_1'],
                                row['opsi_2'],
                                row['opsi_3'],
                                row['opsi_4'],
                                row['jawaban']
                            ))
                            inserted_count += 1

                        conn.commit()
                        c.close()
                        conn.close()

                        st.success(f"✅ {inserted_count} soal berhasil disimpan ke database.")

                    except Exception as e:
                        st.error(f"Gagal menyimpan data: {e}")

            except Exception as e:
                st.error(f"❌ Gagal membaca atau menyimpan file: {e}")

    elif metode == "✍️ Input Manual":
        st.markdown("### ✍️ Masukkan Soal Secara Manual")

        with st.form("form_input_manual"):
            matkul = st.text_input("Mata Kuliah")
            pertanyaan = st.text_area("Pertanyaan")
            opsi_1 = st.text_input("Opsi A")
            opsi_2 = st.text_input("Opsi B")
            opsi_3 = st.text_input("Opsi C")
            opsi_4 = st.text_input("Opsi D")
            jawaban = st.selectbox("Jawaban Benar", ["A", "B", "C", "D"])

            submitted = st.form_submit_button("✅ Simpan Soal")
            if submitted:
                conn = mysql.connector.connect(
                    host='localhost',
                    user='root',
                    password='',
                    database='ujian_app'
                )
                c = conn.cursor()
                c.execute("""
                    INSERT INTO soal_ujian (matkul, pertanyaan, opsi_1, opsi_2, opsi_3, opsi_4, jawaban)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (matkul, pertanyaan, opsi_1, opsi_2, opsi_3, opsi_4, jawaban))
                conn.commit()
                c.close()
                conn.close()
                st.success("✅ Soal berhasil disimpan secara manual.")

def kelola_hasil_ujian():
    st.markdown("## 🛠️ Kelola Data Hasil Ujian")
    
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, nama, nim, matkul, skor, waktu FROM hasil_ujian ORDER BY waktu DESC")
        data = c.fetchall()
        c.close()
        conn.close()

        df = pd.DataFrame(data, columns=["ID", "Nama", "NIM", "Mata Kuliah", "Skor", "Waktu"])

        if df.empty:
            st.info("📭 Belum ada data hasil ujian.")
            return

        selected_row = st.selectbox("📋 Pilih Data Ujian untuk Diedit atau Dihapus", df["ID"].astype(str) + " - " + df["Nama"])

    except Exception as e:
        st.error(f"Gagal mengambil data hasil ujian: {e}")

    if selected_row:
        row_id = int(selected_row.split(" - ")[0])
        record = df[df["ID"] == row_id].iloc[0]

        st.write("### ✏️ Edit Nilai")
        new_skor = st.number_input("Skor Baru", min_value=0.0, max_value=100.0, value=float(record["Skor"]))

        if st.button("💾 Simpan Perubahan"):
            c.execute("UPDATE hasil_ujian SET skor = %s WHERE id = %s", (new_skor, row_id))
            conn.commit()
            st.success("✅ Skor berhasil diperbarui.")
            st.rerun()

        if st.button("🗑️ Hapus Data Ini"):
            c.execute("DELETE FROM hasil_ujian WHERE id = %s", (row_id,))
            conn.commit()
            st.warning("🗑️ Data berhasil dihapus.")
            st.rerun()

    c.close()
    conn.close()


def home_page():
    col1, col2 = st.columns([6, 1])  # kolom kiri untuk isi, kanan untuk tombol

    with col2:
        if st.button("🔐 Login"):
            st.session_state["show_login"] = True
            st.rerun()

    st.title("📚 Selamat Datang di Aplikasi Ujian Online")
    st.markdown("""
    Aplikasi ini dirancang untuk:
    - 📖 Menyediakan soal ujian berbasis pilihan ganda.
    - 🧠 Merekam hasil ujian dan menyimpannya di database.
    - 📊 Memudahkan admin dalam memantau hasil ujian mahasiswa.
    - 🛡️ Sistem login aman menggunakan hashing.

    ### Fitur Utama:
    - Login & Register untuk pengguna.
    - Soal pilihan ganda interaktif.
    - Rekap nilai dan penyimpanan otomatis.
    - Admin dapat mengelola data hasil ujian (edit & hapus).
    
    Silakan klik **Login** di kanan atas untuk mulai.
    """)

# =======================
# Halaman Utama (Login/Register)
# =======================
def main():
    
    st.set_page_config(page_title="Aplikasi Ujian", layout="wide")

    if "last_active" in st.session_state:
        if (datetime.datetime.now() - st.session_state["last_active"]).total_seconds() > 600:  # 10 menit
            st.warning("Anda logout otomatis karena tidak aktif.")
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    st.session_state["last_active"] = datetime.datetime.now()

    if "show_login" not in st.session_state:
        st.session_state["show_login"] = False

    if 'admin_logged_in' not in st.session_state:
        st.session_state['admin_logged_in'] = False

    if "login" not in st.session_state:
        st.session_state["login"] = False
        st.session_state["user"] = None

    if st.session_state.get("admin_logged_in", False):
        col1, col2 = st.columns([6, 1])
        with col1:
            st.subheader("👨‍💼 Halaman Admin") # Lihat & Upload Soal Ujian
        with col2:
            if st.button("🔓 Logout"):
                st.session_state['admin_logged_in'] = False
                st.success("Berhasil logout dari akun admin.")
                st.rerun()

        # Admin bisa melihat hasil dan upload soal
        admin_dashboard()

    elif st.session_state.get("login", False):
        col1, col2 = st.columns([6, 1])
        with col1:
            st.subheader("👩‍🎓 Halaman Ujian Mahasiswa")
        with col2:
            if st.button("🔓 Logout"):
                st.session_state["login"] = False
                st.success("Berhasil logout dari akun user.")
                st.rerun()

        # User mengerjakan ujian berdasarkan mata kuliah
        soal_ujian_page_user()



    elif st.session_state.get("login", False):
        soal_ujian_page_user()
        
    
    
        
        
    
    elif st.session_state["show_login"]:
        # menu = st.sidebar.selectbox("Menu", ["Login", "Register"])
        with st.sidebar:
            selected = option_menu("Main Menu", [ "Login", "Register"],
                                   icons=['person', 'pencil'],
                                   menu_icon="cast", default_index=0)

        # Kolom kiri kecil untuk navigasi, kanan besar untuk konten
        col1, col2 = st.columns([1, 3])

        with col2:  # Menampilkan konten di kolom kanan
            if selected == "login":
                login_user()
            elif selected == "register":
                register_user()
    


        if selected == "Login":
            st.subheader("Login (User/Admin)")
            username = st.text_input("Username")
            password = st.text_input("Password", type='password')

            if st.button("Login"):
                if username == "admin" and password == "admin123":
                    st.session_state['admin_logged_in'] = True
                    st.rerun()
                elif login_user(username, password):
                    st.session_state["login"] = True
                    st.session_state["user"] = username
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

        elif selected == "Register":
            st.subheader("Registrasi")
            reg_user = st.text_input("Username Baru")
            reg_pass = st.text_input("Password Baru", type="password")
            if st.button("Register"):
                success, message = register_user(reg_user, reg_pass)
                if success:
                    st.success(message)
                else:
                    st.error(message)


    else:
        home_page()


if __name__ == '__main__':
    main()



