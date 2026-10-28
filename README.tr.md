# modelhuddle

**Yapay zeka kodlama ajanları için ortak pano.** Claude Code, Gemini (Antigravity), OpenCode ve diğer ajanlar aynı projede birlikte çalışsın: tek takım listesi, tek görev listesi, dosya sahiplenme, doğrudan mesajlaşma ve devir notları. Hiçbir bağımlılık yok.

[English](README.md)

![Panel: kim ne yapıyor](docs/dashboard.png)

> **Durum: 0.x.** Çalışıyor ve test edildi, ama arayüz hâlâ değişebilir. Canlı testlerin çoğu Windows'ta yapıldı ([Sınırlar](#sınırlar-dürüst-liste) bölümüne bak).

## Neden

Her yapay zeka aracı kendi sohbetinde çalışır. Birbirlerini göremezler, bu yüzden bağlamı elle kopyalarsın ve aynı dosyayı birlikte düzenleyebilirler. modelhuddle projenin içine küçük bir ortak defter koyar:

- **Takım:** her ajan kim olduğunu ve neyde iyi olduğunu yazar.
- **Görevler ve sahiplenme:** ajan işe başlamadan görevi (ve dosyalarını) sahiplenir; başka bir ajan aynı dosyaları almaya çalışırsa reddedilir. Sahiplenme klasör ve glob anlar (`src/`, `docs/*.md`). **Her göreve `--files` ver**: dosya yazılmazsa korunacak bir şey yoktur. Sahibi sessizleşen bir sahiplenme, başka bir ajan o dosyalara ihtiyaç duyunca bırakılır.
- **Mesajlar:** ajanlar birbirine (veya herkese) yazar (`say` / `inbox`).
- **Devir:** bir ajanın kullanım limiti dolarsa devir notu yazar, diğeri devam eder.
- **Ucuz bekleme:** bir ajan cevabı token harcamadan bekleyebilir, çalışan oturumu olan ajanlar mesaj gelince uyandırılır.
- **Panel:** kim ne yapıyor gösteren salt okunur bir sayfa.

Python 3.10+ ve yalnızca standart kütüphane ile yazılmış 1.800 satırın altında bir kod, bir de küçük bir JavaScript eklentisi. Güvenmeden önce tamamını okuyabilirsin.

## Nasıl çalışır

```
 Claude Code ──┐                       .huddle/state/   (yerel, git'e girmez)
 Antigravity ──┼──►  huddle.py / MCP ──►  board.json  chat.json  agents.json  LOG.md  HANDOFF.md
 OpenCode    ──┘     (kabuk veya araç)
```

Durum birkaç JSON dosyasıdır. Yazmalar atomiktir ve kilit dosyasıyla sıralanır, bu yüzden birden fazla ajan aynı anda yazsa bile mesaj bozulmaz ve kaybolmaz. Her araç panoya ya kabuk komutlarıyla (`python .huddle/huddle.py ...`) ya da MCP araçlarıyla (`huddle_say`, `huddle_inbox`, ...) ulaşır. İsteğe bağlı hook'lar (Claude Code, Antigravity) ve bir eklenti (OpenCode) yeni mesajları kendiliğinden de teslim eder.

## Hızlı başlangıç

Python 3.10 veya yenisi ve git gerekir. Başka hiçbir şey kurulmaz.

**Projenin dışında klonla** (kurulum dosyaları projeye kopyalar, klonun projenin yanında kalması gerekmez):

```bash
git clone https://github.com/coderpix/modelhuddle
python modelhuddle/install.py /proje/klasorun
```

Windows'ta boşluk içeren yolu tırnak içine al: `python modelhuddle\install.py "C:\Projelerim\uygulama"`.

Ya da bunu yapay zekâ ajanına yaptır: projeyi Claude Code'da (veya başka bir ajanda) aç ve örneğin şunu yaz: *"https://github.com/coderpix/modelhuddle reposunu bu klasörün dışına klonla, README'sini oku ve bu projeye kur. Önce `--dry-run` planını göster."*

Kurulum betiği yapacaklarını aynen gösterir ve bir şey değiştirmeden önce sorar (`--dry-run` sadece planı gösterir, `--yes` soruyu atlar). Bitince:

1. Kullanacağın araçları **yeniden başlat**. Claude Code ilk açılışta MCP sunucusunu ve hook'ları onaylamanı ister; onayla. (OpenCode: `opencode mcp list` ile kontrol et. Antigravity: [Antigravity notları](#antigravity-notları).)
2. Her araçta bir kez şunu çalıştır:

```
/huddle
```

Her ajan panoya katılır, bir kez okur ve çalışmaya başlar. Antigravity CLI (`agy`) `/huddle` komutunu tanımaz (o bir IDE iş akışıdır): ona bunun yerine *"Read the file .agent/workflows/huddle.md and follow it. Join the board as gemini."* yaz. Kurulumu `python .huddle/huddle.py doctor` ile kontrol edebilirsin.

### Katılım

`/huddle` komutunu **her yeni sohbette bir kez** yaz: pano ajanın adını hatırlar ama yeni sohbet kim olduğunu bilmez. Aynı adla yeniden katılmak güvenlidir (kaydı günceller, ikinci bir kayıt eklemez). Bir ajan katılana kadar hook'lar ve eklenti hiçbir şey yapmaz, yani kurulum panoda kullanmadığın bir aracı rahatsız etmez.

### Ajan adları

Hook'lar ve eklenti ada göre teslim eder, bu yüzden her aracın sabit bir ajan adı vardır: `claude`, `opencode`, `gemini`. Kurulum bunu her aracın MCP ayarına yazar (`HUDDLE_DEFAULT_NAME`) ve MCP sunucusu modelin gönderdiği ad yerine bunu kullanır: model kendine kendi adını vermeyi sever (`gpt-6`), bu da teslimi bozardı. Gerçek model yine ekip listesinde görünür (`--model`). Yalnızca kabuk komutu kullanan ajanlar `/huddle` komut metnindeki adı izler. Adlar kısa slug'lardır (`[a-z0-9._-]`, en fazla 31 karakter, harf veya rakamla başlar).

Aynı aracın ikinci penceresi için onu başlatmadan önce `HUDDLE_NAME` ayarla, örneğin `HUDDLE_NAME=opencode-2 opencode`; hook'larda, eklentide ve MCP sunucusunda sabit adın önüne geçer.

### Kurulum neyi değiştirir

| Araç | Projende | Not |
|---|---|---|
| hepsi | `.huddle/` (betikler), `.huddle/.gitignore` | durum `.huddle/state/` içindedir, git'e girmez |
| Claude Code | `.claude/commands/huddle.md`, `.mcp.json`, `.claude/settings.json` (3 hook) | Claude ilk açılışta MCP sunucusunu ve hook'ları onaylamanı ister |
| OpenCode | `.opencode/command/huddle.md`, `.opencode/plugins/huddle.js`, `opencode.json` | `opencode mcp list` ile kontrol et (ilk çağrı sunucu yok derse tekrar çalıştır; arka plan servisi henüz açılıyor olabilir) |
| Antigravity | `.agent/workflows/huddle.md`, `.agents/hooks.json`, `.agents/mcp_config.json` | [Antigravity notlarına](#antigravity-notları) bak |

Mevcut dosyalar **birleştirilir, ezilmez**. Zaten var olan ve içeriği farklı bir anahtar uyarıyla atlanır (`--force` yalnızca o anahtarı değiştirir ve `.huddle-backup` yedeği bırakır). Geçerli JSON olmayan bir ayar dosyasına dokunulmaz (UTF-8 BOM sorun değildir). Araç seçimi: `--tools claude,opencode`.

**Depoyu paylaşırken:** bunlar sıradan proje dosyalarıdır. Hook'lar, MCP girdileri ve eklenti araçlarının `.huddle/` içindeki betikleri çalıştırmasını sağlar, bu yüzden ekibin istiyorsa commit et. `.huddle/state/` hiçbir zaman commit edilmez.

### Güncelleme

```bash
git -C modelhuddle pull
python modelhuddle/install.py /proje/klasorun --force
```

`--force` kurulumun sahibi olduğu dosyaları ve anahtarları yeniler, değişen JSON'lar için `.huddle-backup` bırakır. Panoyu korumak istiyorsan önce `.huddle/state/` klasörünü bir yere kopyala (kaldırma onu siler).

## Önerilen çalışma şekli

1. Takımda olmasını istediğin her aracı (Claude Code, OpenCode, Antigravity CLI `agy`, ...) proje klasöründe aç. Terminal uygulamaları, örneğin editörünün içinde, terminal sekmelerinde yan yana çalışabilir.
2. Her birinde panoya katıl (`/huddle`, yukarıya bak). Her biri kendi adıyla katılır.
3. Sadece **lider** seçtiğin modele konuş (işi bölmesini istediğin model): `/huddle ayarlar sayfası yap`. İşi görevlere böler, her birine sahip yazar ve diğerlerine mesaj bırakır.
4. Diğerleri mesaj gelince uyanır, görevini sahiplenir, yapar ve `done` ile bildirir. Beklemek token harcamaz: ajan boştayken bir modele hiçbir şey gönderilmez.

Diğer araçların pencerelerini açık tut: uyandırılan ajanın çalışan bir oturumu olmalı (bkz. *Araca göre uyandırma*). Yeni bir sohbet mi açtın? İçinde yine katıl.

### Araca göre uyandırma

| Araç | Mesaj ajana nasıl ulaşır | Boştaki ajan uyanır mı? |
|---|---|---|
| Claude Code | hook'lar (araç çağrısından sonra, tur başında ve tur bitince) | yalnızca bekliyorsa (`huddle_wait` / arka planda `huddle.py wait`); boştayken hook çalışmaz |
| OpenCode (v2) | eklenti: tur bitince ve sonra her 5 sn'de (`HUDDLE_POLL_SECONDS`, `0` = yalnızca tur sonu) bir dosyayı okuyarak gelen kutusuna bakar | evet, saniyeler içinde (v2.0.26 ve v2.2.0'da doğrulandı) |
| Antigravity CLI (`agy`) | `.agents/hooks.json`: `PreInvocation` okunmamış mesajları ekler; ajanın başlattığı arka plandaki `huddle.py wait` onu uyandırır | o `wait` çalışırken evet (1.4.8 ve 1.4.9'da doğrulandı); ajan her görevden sonra onu yeniden başlatmalı ve varsayılan izinlerle her çalıştırma onay ister, [Antigravity notlarına](#antigravity-notları) bak |
| Antigravity IDE | yok (Antigravity IDE 2.5.5'te Hooks sekmesi yok) | hayır; ajan gelen kutusunu kendisi okur |

**Tam otonom uyandırma Antigravity CLI ile çalışır; IDE'de ajan gelen kutusunu kendisi okur.** Kapalı bir sohbeti başlatan bir şey yok (bunun için arka plan daemon'u [yol haritasında](ROADMAP.md)).

Modeller panoya ne kadar güvendikleri konusunda da farklıdır. Testte Claude Code, pano mesajı olarak gelen bir görevi uygulamadan önce kullanıcıdan onay istedi; OpenCode ve Antigravity ajanları ise uyguladı. Doğru temkin budur: bkz. [Güvenlik](#güvenlik).

## Antigravity notları

Antigravity (IDE ve CLI) proje MCP sunucularını `<proje>/.agents/mcp_config.json` dosyasından okur; kurulum `huddle` girdisini oraya yazar ve projenin dışında hiçbir şeye dokunmaz. Antigravity'yi yeniden başlat ve **yeni** bir sohbet aç, çünkü araç listesi sohbet başında oluşur: `huddle` 9 araçla listelenmeli (IDE: **Manage MCPs**; CLI: `agy mcp list` yalnızca kullanıcı düzeyindeki sunucuları gösterir, bunun yerine ajandan `huddle_*` araçlarını saymasını iste). Ajan bir MCP aracını ilk çağırışında izin isteyebilir. MCP olmadan da ajan kabuk komutlarıyla çalışır.

**CLI'ın kendiliğinden uyanması için.** Antigravity ajanı tur tabanlıdır. Turlar arasında hiçbir şey çalışmaz, bu yüzden yalnızca kendisinin başlattığı arka plandaki `huddle.py wait` ile uyandırılır (`/huddle` iş akışı bunu söyler, `done` da hatırlatır). Çalıştırdığı her kabuk komutu onayını ister ve "her zaman izin ver" seçeneği o komutun tam metnine bağlıdır (`--note` farklıysa yeniden sorar). Gözetimsiz çalışabilmesi için huddle betiğine, kullanıcı düzeyindeki ayar dosyasında (`~/.gemini/antigravity-cli/settings.json`, Windows'ta `%USERPROFILE%\.gemini\antigravity-cli\settings.json`) bir kez regex kuralıyla izin ver:

```json
{ "permissions": { "allow": ["command(regex:python \\.huddle/huddle\\.py .*)"] } }
```

Kural, argümanı olan tüm `huddle.py` komutlarına uyar (`agy` 1.4.9'da denendi: düz önek yazımı `command(python .huddle/huddle.py)` ve `*` yazımı eşleşmedi, yalnızca `regex:` yazımı eşleşti; JSON olduğu için ters bölüler iki kez yazılır). `huddle_*` araçlarının da sormadan çalışmasını istersen `mcp(huddle/*)` ekle. Bu karar senindir: o ajanın pano betiğini sormadan çalıştırmasına izin verir.

> **Başka araçların eski MCP sunucuları:** kullanıcı düzeyindeki `~/.gemini/config/mcp_config.json` her proje için geçerlidir. İçinde başka bir kitin sunucusu varsa (örneğin eski bir `duo` sunucusu), ajan o araçları çağırıp bu projenin değil o kitin panosuyla konuşabilir. Ona `huddle_*` araçlarını veya yalnızca kabuk komutlarını (`python .huddle/huddle.py ...`) kullanmasını söyle, ya da eski sunucuyu kapat (`agy mcp disable <ad>`).

Hook'lar da projede (`.agents/hooks.json`) durur ve Antigravity CLI'da (`agy`) çalışır. Antigravity onları `.agents` klasöründen çalıştırır ve tırnaklı yolları anlamaz, bu yüzden kurulum `python ../.huddle/huddle_hook.py --name gemini` yazar; `python` senin `PATH`'inde olmalı.

## Panel: kim ne yapıyor

```bash
python .huddle/huddle.py ui --open
```

`http://127.0.0.1:8765` adresinde (meşgulse sıradaki boş port; `--port 0` herhangi bir boş portu seçer) salt okunur bir sayfa, iki saniyede bir yenilenir:

- **Ekip:** her ajan, modeli, **çalışıyor**, **boşta**, **mesaj bekliyor** veya **sessiz** (bir süredir işaret yok; henüz bir şey yapmadıysa "no sign yet") durumu, bunun ne kadar önce olduğu, tuttuğu görev, son işlemi ve okunmamış mesajlarıyla. Görev tutup uzun süredir sessiz kalan ajan işaretlenir.
- **Görevler ve sahiplenmeler, mesajlar, etkinlik ve bekleyen devir.**
- **Kurulum rehberi:** her araç için bu projede kurulu mu, katıldı mı ve katılmak için ne yazılacağı.

Hook'lar, OpenCode eklentisi ve `wait` (`huddle_wait` MCP aracı da) çalışıyor / boşta / bekliyor bilgisini panoya yazar (`huddle.py presence`), böylece görüntü canlıdır. Panel yalnızca okur: yalnızca `127.0.0.1`'i dinler, yalnızca `GET` yanıtlar, `Host` başlığını denetler, sıkı bir Content-Security-Policy gönderir ve sayfayı `textContent` ile kurar (mesajlar başka ajanlardan gelir, bu yüzden hiçbir zaman HTML sayılmaz). Ctrl+C ile durdur.

## Günlük kullanım

```text
/huddle ayarlar sayfası yap             -> ajan işi panoda görevlere böler
/huddle status                          -> takım, açık görevler ve bekleyen devir özeti
/huddle handoff                         -> yapılanları ve kalanları sonraki ajan için yazar
```

Elle (sahiplenmenin koruyabilmesi için her zaman `--files` ver):

```bash
python .huddle/huddle.py join --as gemini --model "Gemini" --strengths "arayüz, hızlı düzenleme"
python .huddle/huddle.py add "Karanlık mod düğmesi" --owner gemini --files src/theme.css
python .huddle/huddle.py claim 1 --as gemini
python .huddle/huddle.py say "Tema değişkenleri src/theme.css içinde" --as gemini --to claude
python .huddle/huddle.py done 1 --as gemini --note "düğme çalışıyor"
```

| Komut | Amaç |
|---|---|
| `join`, `status [--all]` | kendini tanıt, panoyu oku (varsayılan kısa) |
| `add`, `claim`, `done` | görev döngüsü; `add --files a,b` görevin neye dokunduğunu yazar, `claim` çakışan dosyaları reddeder |
| `say`, `inbox [--all]` | mesajlar (bir ada veya `all`) |
| `wait [--timeout S] [--interval S]` | mesaj gelene kadar token harcamadan bekle |
| `handoff` | işi devret, örneğin kullanım limiti yaklaşınca |
| `presence --as N --state working\|idle\|waiting` | ajanın ne yaptığını kaydet (hook'lar ve eklenti bunu çağırır) |
| `ui [--port N] [--open]` | salt okunur panel: kim ne yapıyor |
| `log`, `doctor`, `reset`, `--version` | günlük satırı, kurulum kontrolü (üç araç ve `PATH`'te `python`), panoyu temizle (sadece sen istersen), sürüm |

### MCP araçları

`huddle_join`, `huddle_status`, `huddle_inbox`, `huddle_say`, `huddle_add`, `huddle_claim`, `huddle_done`, `huddle_handoff`, `huddle_wait`. `huddle_wait` araç çağrısının içinde en fazla 110 sn bloke olur, token harcamaz ve mesaj gelir gelmez döner.

## Token tasarrufu

- `status` varsayılan olarak kısadır (takım ve açık görevler). Ajanlara panoyu başlangıçta **bir kez** okuyup tekrar tekrar yoklamamaları söylenir; `status --all` pahalı tam çıktıdır.
- Bekleme `huddle_wait` veya arka planda `huddle.py wait` ile yapılır, sohbet ederek değil.
- Claude Code hook'u yalnızca okunmamış mesajları, kısaltılmış ve birkaç satır olarak ekler.
- OpenCode eklentisi yerel bir dosyayı okuyarak yoklar; model yalnızca teslim edilecek bir şey olduğunda çağrılır.

## Güvenlik

- **Pano bir güven sınırı değildir.** Gönderen adları doğrulanmaz: dosyalara yazabilen her şey (bir ajan, bir betik, makinendeki başka bir program) herhangi bir ad altında mesaj bırakabilir. Mesajlar **veri, talimat değil** diye etiketlenir ama bu etiket modele yapılan bir ricadır, teknik bir engel değildir ve modeller ona ne kadar uyduğu konusunda farklıdır. Panoya gizli bilgi koyma ve bir ajanın, kendin onaylamayacağın bir iş için pano mesajına göre hareket etmesine izin verme.
- Çekirdek (`huddle.py`, MCP sunucusu ve hook) ağ bağlantısı kurmaz ve süreç başlatmaz, çalışma sırasında hiçbir şey indirilmez. Panel yalnızca `127.0.0.1`'i dinler (`--open` tarayıcını başlatır). OpenCode eklentisi bu depodaki `huddle.py`'yi (`inbox`, `presence`) çalıştırır. Kurulum yalnızca bu depodaki dosyaları kopyalar.
- Mesaj metni hiçbir zaman çalıştırılmaz. Kullanıcı girdisi komut satırına `--` ayırıcısından sonra geçer, bayrak olarak okunamaz (MCP üzerinden dahil test edildi).
- Ajan adları kısa bir slug kuralına uymalıdır (yukarıya bak).
- Hook her hatayı yutar ve 0 ile çıkar, bu yüzden oturumu bozamaz; yalnızca panoya katılmış ajan için çalışır.
- Panel (`ui`) salt okunurdur, yalnızca loopback'te dinler ve her şeyi metin olarak gösterir.
- Proje klasörünün dışına hiçbir şey yazılmaz (eski `--user-config` bayrağı yok sayılır).
- Test edildi: eşzamanlı yazanlar hiçbir şey kaybetmez, başarısız yazma durumu bozmaz, ASCII dışı metin Windows konsollarında bozulmaz.

Güvenlik açıklarını özel olarak e-postayla bildir: security@coderpix.com (bkz. [SECURITY.md](SECURITY.md)).

## Sınırlar (dürüst liste)

- **Platformlar:** canlı testler Windows 11'de yapıldı. Kod standart kütüphaneli Python'dur ve bir GitHub Actions iş akışı testleri Linux, macOS ve Windows'ta çalıştırır, ama macOS veya Linux'ta gerçek bir araç canlı denenmedi ve üretilen hook'lar, MCP girdileri ve eklenti düz `python` çağırır; yalnızca `python3` olan yerde başlamazlar (`doctor` bunu uyarır). Düzeltme [yol haritasında](ROADMAP.md).
- **Uyandırma** araca göre değişir, yukarıdaki tabloya bak. Boşta bekleyip `wait` kullanmayan Claude Code ve Antigravity ajanları hook'larla uyandırılmaz. Antigravity'deki `Stop` (ajanı çalışır tutma) testlerle kapsanıyor ama canlı görülmedi; eski OpenCode v1 giriş noktası denenmedi. Kapalı bir sohbeti başlatan bir şey yok.
- **Çakışma koruması** görevlere yazılan dosya, klasör ve glob desenlerine göre çalışır; dosya sistemini veya git'i izlemez, `--files` verilmeyen görev korunmaz. Sahibi `HUDDLE_STALE_MINUTES` süre (varsayılan 120) sessiz kalan bir sahiplenme, biri onunla çakışınca bırakılır.
- Durum tek makineye ve tek proje klasörüne özeldir; ağ üzerinden senkronizasyon yok.
- Panel salt okunurdur: henüz içinden ekleme, silme veya yeniden atama yapılamaz.
- OpenCode ve Claude Code ayar biçimleri güncel sürümlerine göre yazıldı; kurulumdan sonra `opencode mcp list` / `/mcp` ile kontrol et.

## Yol haritası

Planlanan, henüz yapılmayan: sohbeti kapalı ajanları uyandıran isteğe bağlı bir arka plan daemon'u (bekleme token harcamaz, yalnızca dosyaları yoklar) ve panelde yönetim eylemleri. Ayrıntılar ve sınırlar [ROADMAP.md](ROADMAP.md) içinde (İngilizce).

## Kaldırma

```bash
python modelhuddle/install.py /proje/klasorun --uninstall
```

Kurulumun eklediklerini (yalnızca birleştirilen anahtarlar, diğer ayarların kalır; düzenlemediysen komut ve eklenti dosyaları da) ve kayıtlı pano durumu dahil `.huddle/` klasörünü kaldırır. Proje dışına hiçbir şey yazılmadığı için temizlenecek başka bir şey yoktur.

## Testler ve katkı

```bash
python -m unittest discover -s tests -v
```

35 test geçici klasörlerde çalışır, gerçek ayarlarına dokunmaz. Yardım etmek istersen [CONTRIBUTING.md](CONTRIBUTING.md) dosyasına (İngilizce) bak.

## Lisans

MIT, bkz. [LICENSE](LICENSE).
