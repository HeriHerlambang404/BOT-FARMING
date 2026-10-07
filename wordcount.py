import os
import sys
from pyspark import SparkConf, SparkContext
# 1. Pastikan Spark JVM memanggil interpreter Python yang sedang aktif
os.environ["PYSPARK_PYTHON"] = sys.executable
os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable
# 2. Paksa Spark mengikat komunikasi lokal ke 127.0.0.1 (mencegah konflik adapter/VPN)
conf = (
SparkConf()
.setAppName("WordCountApp")
.setMaster("local[*]")
.set("spark.driver.host", "127.0.0.1")
.set("spark.driver.bindAddress", "127.0.0.1")
)
# 3. Inisialisasi SparkContext dengan konfigurasi di atas
sc = SparkContext(conf=conf)
# 4. Membaca file teks menjadi RDD
teks_rdd = sc.textFile("data.txt")
# 5. Transformasi (Lazy Evaluation)
kata_rdd = teks_rdd.flatMap(lambda baris: baris.split(" "))
pasangan_rdd = kata_rdd.map(lambda kata: (kata, 1))
hasil_rdd = pasangan_rdd.reduceByKey(lambda a, b: a + b)
# 6. Aksi (Eksekusi Komputasi)
hasil = hasil_rdd.collect()
print("\n" + "=" * 30)
print("HASIL PERHITUNGAN KATA:")
print("=" * 30)
for kata, jumlah in hasil:
    if kata.strip(): # Mengabaikan string kosong jika ada spasi ganda
        print(f"{kata:<15}: {jumlah}")
print("=" * 30 + "\n")
# 7. Hentikan SparkContext
sc.stop()