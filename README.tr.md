# modelhuddle

**Yapay zeka kodlama ajanları için ortak pano.** Claude Code, Gemini (Antigravity), OpenCode ve diğer ajanlar aynı projede birlikte çalışsın: tek takım listesi, tek görev listesi, dosya sahiplenme, doğrudan mesajlaşma ve devir notları. Hiçbir bağımlılık yok.

[English](README.md)

## Neden

Her yapay zeka aracı kendi sohbetinde çalışır. Birbirlerini göremezler, bu yüzden bağlamı elle kopyalarsın ve aynı dosyayı birlikte düzenleyebilirler. modelhuddle projenin içine küçük bir ortak defter koyar:

- **Takım:** her ajan kim olduğunu ve neyde iyi olduğunu yazar.
- **Görevler ve sahiplenme:** ajan işe başlamadan görevi (ve dosyalarını) sahiplenir; başka bir ajan aynı dosyaları almaya çalışırsa reddedilir. Sahiplenme klasör ve glob anlar (`src/`, `docs/*.md`), sahibi sessizleşen bir sahiplenme kendiliğinden bırakılır.
- **Mesajlar:** ajanlar birbirine (veya herkese) yazar (`say` / `inbox`).
- **Devir:** bir ajanın kullanım limiti dolarsa devir notu yazar, diğeri devam eder.
- **Ucuz bekleme:** bir ajan cevabı token harcamadan bekleyebilir, boştaki ajanlar mesaj gelince uyandırılır.

Python 3.10+ ve yalnızca standart kütüphane ile yazılmış birkaç yüz satırlık bir koddur. Güvenmeden önce tamamını okuyabilirsin.

## Nasıl çalışır

```
 Claude Code ──┐                       .huddle/state/   (yerel, git'e girmez)
 Antigravity ──┼──►  huddle.py / MCP ──►  board.json  chat.json  agents.json  LOG.md
 OpenCode    ──┘     (kabuk veya araç)
```

Durum birkaç JSON dosyasıdır. Yazmalar atomiktir ve kilit dosyasıyla sıralanır, bu yüzden birden fazla ajan aynı anda yazsa bile mesaj bozulmaz ve kaybolmaz. Her araç panoya ya kabuk komutlarıyla (`python .huddle/huddle.py ...`) ya da MCP araçlarıyla (`huddle_say`, `huddle_inbox`, ...) ulaşır. İsteğe bağlı hook'lar (Claude Code, Antigravity) ve bir eklenti (OpenCode) yeni mesajları kendiliğinden de teslim eder.

## Hızlı başlangıç

Python 3.10 veya yenisi ve git gerekir. Başka hiçbir şey kurulmaz.

```bash
git clone https://github.com/coderpix/modelhuddle
python modelhuddle/install.py /proje/klasorun
```

Ya da bunu yapay zekâ ajanına yaptır: projeyi Claude Code'da (veya başka bir ajanda) aç ve örneğin şunu yaz: *"https://github.com/coderpix/modelhuddle reposunu bu klasörün dışına klonla, README'sini oku ve bu projeye kur. Önce `--dry-run` planını göster."*

Kurulum betiği yapacaklarını aynen gösterir ve bir şey değiştirmeden önce sorar (`--dry-run` sadece planı gösterir, `--yes` soruyu atlar). Bitince:

1. Kullanacağın araçları **yeniden başlat**. Claude Code ilk açılışta MCP sunucusunu ve hook'ları onaylamanı ister; onayla. (OpenCode: `opencode mcp list` ile kontrol et. Antigravity: aşağıdaki bölüme bak.)
2. Her araçta bir kez şunu çalıştır:

```
/huddle
```

Her ajan kısa bir ad seçer, panoya katılır, bir kez okur ve çalışmaya başlar. Kurulumu `python .huddle/huddle.py doctor` ile kontrol edebilirsin.

`/huddle` komutunu **her yeni sohbette bir kez** yaz: pano ajanın adını hatırlar ama yeni sohbet kim olduğunu bilmez. Aynı adla yeniden katılmak güvenlidir (kaydı günceller, ikinci bir kayıt eklemez). Bir ajan katılana kadar hook'lar ve eklenti hiçbir şey yapmaz, yani kurulum panoda kullanmadığın bir aracı rahatsız etmez. Hook'lar ve eklenti ada göre teslim eder, bu yüzden her aracın sabit bir ajan adı vardır: `claude`, `opencode`, `gemini`. Kurulum bunu her aracın MCP ayarına yazar (`HUDDLE_DEFAULT_NAME`) ve MCP sunucusu modelin gönderdiği ad yerine bunu kullanır: model kendine kendi adını vermeyi sever (`gpt-6`), bu da teslimi bozardı. Gerçek model yine ekip listesinde görünür (`--model`). Aynı aracın ikinci penceresi için onu başlatmadan önce `HUDDLE_NAME` ayarla, örneğin `HUDDLE_NAME=opencode-2 opencode`; hook'larda, eklentide ve MCP sunucusunda sabit adın önüne geçer. Yalnızca kabuk komutu kullanan ajanlar `/huddle` komut metnindeki adı izler.

### Kurulum neyi değiştirir

| Araç | Projende | Not |
|---|---|---|
| hepsi | `.huddle/` (betikler), `.huddle/.gitignore` | durum `.huddle/state/` içindedir, git'e girmez |
| Claude Code | `.claude/commands/huddle.md`, `.mcp.json`, `.claude/settings.json` (3 hook) | Claude ilk açılışta MCP sunucusunu ve hook'ları onaylamanı ister |
| OpenCode | `.opencode/command/huddle.md`, `.opencode/plugins/huddle.js`, `opencode.json` | `opencode mcp list` ile kontrol et (ilk çağrı sunucu yok derse tekrar çalıştır; arka plan servisi henüz açılıyor olabilir) |
| Antigravity | `.agent/workflows/huddle.md`, `.agents/hooks.json`, `.agents/mcp_config.json` | aşağıdaki Antigravity bölümüne bak |

Mevcut dosyalar **birleştirilir, ezilmez**. Zaten var olan ve içeriği farklı bir anahtar uyarıyla atlanır (`--force` yalnızca o anahtarı değiştirir ve `.huddle-backup` yedeği bırakır). Geçerli JSON olmayan bir ayar dosyasına dokunulmaz. Araç seçimi: `--tools claude,opencode`.

### Antigravity (Gemini)

Antigravity (IDE ve CLI) proje MCP sunucularını `<proje>/.agents/mcp_config.json` dosyasından okur; kurulum `huddle` girdisini oraya yazar ve projenin dışında hiçbir şeye dokunmaz. Antigravity'yi yeniden başlat ve **yeni** bir sohbet aç, çünkü araç listesi sohbet başında oluşur: `huddle` 9 araçla listelenmeli (IDE: **Manage MCPs**; CLI: `agy mcp list` yalnızca kullanıcı düzeyindeki sunucuları gösterir, bunun yerine ajandan `huddle_*` araçlarını saymasını iste). Ajan bir MCP aracını ilk çağırışında izin isteyebilir. MCP olmadan da ajan kabuk komutlarıyla çalışır.

> **Başka araçların eski MCP sunucuları:** kullanıcı düzeyindeki `~/.gemini/config/mcp_config.json` her proje için geçerlidir. İçinde başka bir kitin sunucusu varsa (örneğin eski bir `duo` sunucusu), ajan o araçları çağırıp bu projenin değil o kitin panosuyla konuşabilir. Ona `huddle_*` araçlarını veya yalnızca kabuk komutlarını (`python .huddle/huddle.py ...`) kullanmasını söyle, ya da eski sunucuyu kapat (`agy mcp disable <ad>`).

Hook'lar da projede (`.agents/hooks.json`) durur ve Antigravity CLI'da (`agy`) çalışır. Antigravity onları `.agents` klasöründen çalıştırır ve tırnaklı yolları anlamaz, bu yüzden kurulum `python ../.huddle/huddle_hook.py --name gemini` yazar; `python` senin `PATH`'inde olmalı.

## Önerilen çalışma şekli

1. Takımda olmasını istediğin her aracı (Claude Code, OpenCode, Antigravity CLI `agy`, ...) proje klasöründe aç. Terminal uygulamaları, örneğin editörünün içinde, terminal sekmelerinde yan yana çalışabilir.
2. Her birinde bir kez `/huddle` yaz. Her biri kendi adıyla panoya katılır.
3. Sadece ana beyin seçtiğin modele konuş: `/huddle ayarlar sayfası yap`. İşi görevlere böler, her birine sahip yazar ve diğerlerine mesaj bırakır.
4. Diğerleri mesaj gelince uyanır, görevini sahiplenir, yapar ve `done` ile bildirir. Beklemek token harcamaz: ajan boştayken bir modele hiçbir şey gönderilmez.

Diğer araçların pencerelerini açık tut: uyandırılan ajanın çalışan bir oturumu olmalı (bkz. *Araca göre uyandırma*). Yeni bir sohbet mi açtın? İçinde yine `/huddle` yaz.

### Araca göre uyandırma

| Araç | Mesaj ajana nasıl ulaşır | Boştaki ajan uyanır mı? |
|---|---|---|
| Claude Code | hook'lar (araç çağrısından sonra, tur başında ve tur bitince) | yalnızca bekliyorsa (`huddle_wait` / arka planda `huddle.py wait`); boştayken hook çalışmaz |
| OpenCode (v2) | eklenti: tur bitince ve sonra her 5 sn'de (`HUDDLE_POLL_SECONDS`, `0` = yalnızca tur sonu) bir dosyayı okuyarak gelen kutusuna bakar | evet, saniyeler içinde (v2.0.26 ve v2.2.0'da doğrulandı) |
| Antigravity CLI (`agy`) | `.agents/hooks.json`: `PreInvocation` okunmamış mesajları ekler | çalışırken veya beklerken; `Stop` ajanı çalışır tutar ama canlı görülmedi |
| Antigravity IDE | yok (denediğim sürümde Hooks sekmesi yok) | hayır; ajan gelen kutusunu kendisi okur |

Kapalı bir sohbeti başlatan bir şey yok.

## Günlük kullanım

```text
/huddle ayarlar sayfası yap             -> ajan işi panoda görevlere böler
/huddle status                          -> takım, açık görevler ve bekleyen devir özeti
/huddle handoff                         -> yapılanları ve kalanları sonraki ajan için yazar
```

Elle:

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
| `add`, `claim`, `done` | görev döngüsü; `claim` çakışan dosyaları reddeder |
| `say`, `inbox [--all]` | mesajlar (bir ada veya `all`) |
| `wait [--timeout S]` | mesaj gelene kadar token harcamadan bekle |
| `handoff` | işi devret, örneğin kullanım limiti yaklaşınca |
| `log`, `doctor`, `reset` | günlük satırı, kurulum kontrolü, panoyu temizle (sadece sen istersen) |

### MCP araçları

`huddle_join`, `huddle_status`, `huddle_inbox`, `huddle_say`, `huddle_add`, `huddle_claim`, `huddle_done`, `huddle_handoff`, `huddle_wait`. `huddle_wait` araç çağrısının içinde en fazla 110 sn bloke olur, token harcamaz ve mesaj gelir gelmez döner.

## Token tasarrufu

- `status` varsayılan olarak kısadır (takım ve açık görevler). Ajanlara panoyu başlangıçta **bir kez** okuyup tekrar tekrar yoklamamaları söylenir; `status --all` pahalı tam çıktıdır.
- Bekleme `huddle_wait` veya arka planda `huddle.py wait` ile yapılır, sohbet ederek değil.
- Claude Code hook'u yalnızca okunmamış mesajları, kısaltılmış ve birkaç satır olarak ekler.
- OpenCode eklentisi yerel bir dosyayı okuyarak yoklar; model yalnızca teslim edilecek bir şey olduğunda çağrılır.

## Güvenlik

- Yalnızca standart kütüphane; ağ erişimi yok, çalışma sırasında hiçbir şey indirilmez. Hook'lar yalnızca `huddle_hook.py`'yi, OpenCode eklentisi yalnızca bu depodaki `huddle.py`'yi (`inbox`) çalıştırır. Kurulum yalnızca bu depodaki dosyaları kopyalar.
- Diğer ajanlardan gelen mesajlar **veri, talimat değil** olarak etiketlenir; mesaj metni hiçbir zaman çalıştırılmaz.
- Kullanıcı girdisi komut satırına `--` ayırıcısından sonra geçer, bayrak olarak okunamaz (MCP üzerinden dahil test edildi).
- Ajan adları kısa bir slug kuralına uymalıdır (`[a-z0-9._-]`, en fazla 31 karakter).
- Hook her hatayı yutar ve 0 ile çıkar, bu yüzden oturumu bozamaz; yalnızca panoya katılmış ajan için çalışır.
- Proje klasörünün dışına hiçbir şey yazılmaz (eski `--user-config` bayrağı yok sayılır).
- Test edildi: eşzamanlı yazanlar hiçbir şey kaybetmez, başarısız yazma durumu bozmaz, ASCII dışı metin Windows konsollarında bozulmaz.

Güvenlik açıklarını özel olarak e-postayla bildir: security@coderpix.com (bkz. [SECURITY.md](SECURITY.md)).

## Sınırlar (dürüst liste)

- Uyandırma araca göre değişir, yukarıdaki tabloya bak. Boşta bekleyip `wait` kullanmayan Claude Code ve Antigravity ajanları hook'larla uyandırılmaz. Antigravity'deki `Stop` (ajanı çalışır tutma) testlerle kapsanıyor ama canlı görülmedi; eski OpenCode v1 giriş noktası denenmedi. Kapalı bir sohbeti başlatan bir şey yok.
- Çakışma koruması, görevlere yazılan dosya, klasör ve glob desenlerine göre çalışır; dosya sistemini veya git'i izlemez. Sahibi `HUDDLE_STALE_MINUTES` süre (varsayılan 120) sessiz kalan bir sahiplenme, biri onunla çakışınca bırakılır.
- Durum tek makineye ve tek proje klasörüne özeldir; ağ üzerinden senkronizasyon yok.
- Panel yok. hcom veya Concord MCP gibi projeler daha fazla özellik sunar (daha çok araçta boşta uyandırma, daha zengin çakışma yönetimi, arayüz); modelhuddle bunların yerine küçük, bağımlılıksız ve denetlenebilir olmayı seçer.
- OpenCode ve Claude Code ayar biçimleri güncel sürümlerine göre yazıldı; kurulumdan sonra `opencode mcp list` / `/mcp` ile kontrol et.

## Kaldırma

```bash
python modelhuddle/install.py /proje/klasorun --uninstall
```

Kurulumun eklediklerini (yalnızca birleştirilen anahtarlar, diğer ayarların kalır) ve kayıtlı pano durumu dahil `.huddle/` klasörünü kaldırır. Kullanıcı düzeyindeki dosyalar kendiliğinden kaldırılmaz.

## Testler

```bash
python -m unittest discover -s tests -v
```

25 test geçici klasörlerde çalışır, gerçek ayarlarına dokunmaz.

## Lisans

MIT, bkz. [LICENSE](LICENSE).
