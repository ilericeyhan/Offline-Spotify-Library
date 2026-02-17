# Offline Spotify Kütüphanesi

**Spotify kütüphanenizi yönetebileceğiniz güçlü ve modern bir uygulama.**

Bu uygulama, `spotdl` için gelişmiş bir arayüz sağlar. Çalma listelerinizi senkronize edebilir, düzenleyebilir ve müziklerinizi çevrimdışı dinlemek üzere klasörleyebilirsiniz.

## 💾 İndir

**Windows**, **macOS** ve **Linux** için hazır dosyaları [GitHub Releases](https://github.com/ilericeyhan/Offline-Spotify-Library/releases) sayfasında bulabilirsiniz. Python kurulumu gerektirmez!

## 🚀 Temel Özellikler

### 📚 Akıllı Kütüphane Yönetimi
*   **Kalıcı Kütüphane**: En sevdiğiniz listeleri takip edin ve her zaman güncel tutun.
*   **Görsel Düzenleme**: Klasörler oluşturun, çalma listelerini türlerine göre gruplayın ve **Sürükle-Bırak** ile sıralayın.
*   **Modern Arayüz**: Şık karanlık tema ve hızlı tepki veren tasarım.

### 🔄 Akıllı Senkronizasyon Durumu
Kütüphanenizin durumunu **Akıllı İkonlar** ile bir bakışta görün:
*   🟢 **Senkron**: Spotify ile tamamen aynı.
*   🔄 **Yeni Şarkılar**: Spotify'da yeni şarkılar tespit edildi.
*   ⚠️ **Kesildi**: Son eşitleme denemesi yarıda kaldı (örneğin hız sınırı nedeniyle).
*   ⚪ **Yeni**: İlk defa eşitlenmeye hazır.

### 🛡️ Spotify Profili ile Entegrasyon
*   **Kopyaları Önleme**: "Profilim" sekmesinde zaten kütüphanenizde olan listeler otomatik olarak işaretlenir ve tekrar indirilmesi önlenir.
*   **Görsel Geri Bildirim**: Senkronizasyon durumlarını doğrudan profil tarayıcısında görebilirsiniz.

---

## 🚀 Başlarken

### Gereksinimler
1.  **Python 3.9+** (Geliştiriciler için).
2.  **FFmpeg** (Sisteminize kurulu ve PATH'e eklenmiş olmalı).
3.  **Spotify API Anahtarları** (Client ID & Secret). Bunları [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) üzerinden alabilirsiniz.

### Kurulum ve Çalıştırma

**macOS / Linux**
1. Klasöre gidin.
2. Çalıştırma betiğini başlatın:
   ```bash
   chmod +x run.sh
   ./run.sh
   ```

**Windows**
1. Klasörde `run.bat` dosyasına çift tıklayın.

### İlk Yapılandırma
1.  **Ayarlar** sekmesine gidin.
2.  **İndirilecek Klasör** yolunu seçin.
3.  **Spotify İstemci Kimliği** ve **Şifre** bilgilerini girin.

---

## ❓ SSS & Sorun Giderme

**S: Senkronizasyon takılıyor veya hata veriyor?**
> **Geçmiş** sekmesine gidin ve hata ayrıntılarını görmek için **"Detaylar"** butonuna tıklayın. Ayrıca **Loglar** sekmesini kontrol edebilirsiniz. Eğer "429" hatası görüyorsanız Spotify size hız sınırı uyguluyor demektir; uygulama bunu yönetir ancak beklemeniz gerekebilir.

**S: Yeni şarkıları neden göremiyorum?**
> Kütüphane sekmesinde **Yenile** butonuna basın. Eğer ikon Turuncuya (🔄) dönerse **Tümünü Eşitle** deyin.

**S: Müzikler nereye kaydediliyor?**
> **Ayarlar** sekmesinde seçtiğiniz klasöre kaydedilir. Her çalma listesi için ayrı bir alt klasör oluşturulur, bireysel "Hızlı İndir" şarkıları ise özel bir **"Quick Downloads"** klasörüne kaydedilir.

---

## 👨‍💻 Hakkında

Müzik severler için ❤️ ile geliştirildi.

**Antigravity tarafından desteklenmektedir**
