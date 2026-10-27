# modelhuddle

**Yapay zeka kodlama ajanları için ortak pano.** Claude Code, Gemini (Antigravity), OpenCode ve diğer ajanlar aynı projede birlikte çalışsın: tek takım listesi, tek görev listesi, dosya sahiplenme, doğrudan mesajlaşma ve devir notları. Hiçbir bağımlılık yok.

[English](README.md)

## Neden

Her yapay zeka aracı kendi sohbetinde çalışır. Birbirlerini göremezler, bu yüzden bağlamı elle kopyalarsın ve aynı dosyayı birlikte düzenleyebilirler. modelhuddle projenin içine küçük bir ortak defter koyar:

- **Takım:** her ajan kim olduğunu ve neyde iyi olduğunu yazar.
- **Görevler ve sahiplenme:** ajan işe başlamadan görevi (ve dosyalarını) sahiplenir; başka bir ajan aynı dosyaları almaya çalışırsa reddedilir.
- **Mesajlar:** ajanlar birbirine (veya herkese) yazar (`say` / `inbox`).
- **Devir:** bir ajanın kullanım limiti dolarsa devir notu yazar, diğeri devam eder.
- **Ucuz bekleme:** bir ajan cevabı token harcamadan bekleyebilir.

Python 3.10+ ve yalnızca standart kütüphane ile yazılmış birkaç yüz satırlık bir koddur. Güvenmeden önce tamamını okuyabilirsin.

## Nasıl çalışır

```
 Claude Code ──┐                       .huddle/state/   (yerel, git'e girmez)
 Antigravity ──┼──►  huddle.py / MCP ──►  board.json  chat.json  agents.json  LOG.md
 OpenCode    ──┘     (kabuk veya araç)
```

Durum birkaç JSON dosyasıdır. Yazmalar atomiktir ve kilit dosyasıyla sıralanır, bu yüzden birden fazla ajan aynı anda yazsa bile mesaj bozulmaz ve kaybolmaz. Her araç panoya ya kabuk komutlarıyla (`python .huddle/huddle.py ...`) ya da MCP araçlarıyla (`huddle_say`, `huddle_inbox`, ...) ulaşır. İsteğe bağlı hook'lar (Claude Code, Antigravity) ve bir eklenti (OpenCode) yeni mesajları kendiliğinden de teslim eder.

## Hızlı başlangıç

```bash
git clone https://github.com/coderpix/modelhuddle
python modelhuddle/install.py /proje/klasorun
```

Kurulum betiği yapacaklarını aynen gösterir ve bir şey değiştirmeden önce sorar (`--dry-run` sadece planı gösterir, `--yes` soruyu atlar). Sonra her araçta şunu çalıştır:

```
/huddle
```

Her ajan kısa bir ad seçer, panoya katılır, bir kez okur ve çalışmaya başlar. Kurulumu `python .huddle/huddle.py doctor` ile kontrol edebilirsin.

### Kurulum neyi değiştirir

| Araç | Projende | Not |
|---|---|---|
| hepsi | `.huddle/` (betikler), `.huddle/.gitignore` | durum `.huddle/state/` içindedir, git'e girmez |
| Claude Code | `.claude/commands/huddle.md`, `.mcp.json`, `.claude/settings.json` (3 hook) | Claude ilk açılışta MCP sunucusunu ve hook'ları onaylamanı ister |
| OpenCode | `.opencode/command/huddle.md`, `opencode.json` | `opencode mcp list` ile kontrol et (ilk çağrı sunucu yok derse tekrar çalıştır; arka plan servisi henüz açılıyor olabilir) |
| Antigravity | `.agent/workflows/huddle.md` | MCP **kullanıcı düzeyinde** bir dosyada durur, aşağıya bak |

Mevcut dosyalar **birleştirilir, ezilmez**. Zaten var olan ve içeriği farklı bir anahtar uyarıyla atlanır (`--force` yalnızca o anahtarı değiştirir ve `.huddle-backup` yedeği bırakır). Geçerli JSON olmayan bir ayar dosyasına dokunulmaz. Araç seçimi: `--tools claude,opencode`.

### Antigravity (Gemini)

Antigravity MCP sunucularını projeden değil **kullanıcı** klasöründen okur, bu yüzden kurulum varsayılan olarak yalnızca eklenecek girdiyi yazdırır. Ya kendin eklersin ya da yedek alarak kuruluma yaptırırsın:

```bash
python install.py /proje/klasorun --user-config
```

Antigravity'nin gerçekten okuduğu dosya `~/.gemini/config/mcp_config.json`'dır (`~/.gemini/antigravity/mcp_config.json` eski, taşınmış konumdur ve okunmaz). `command` alanına Python'un tam yolunu yaz, çünkü IDE farklı bir `PATH` ile çalışıyor olabilir. Düzenledikten sonra Antigravity'yi yeniden başlat ve **Manage MCPs** ekranını aç: `huddle` 9 araçla listelenmeli. **Yeni** bir sohbet aç, çünkü araç listesi sohbet başında oluşur. MCP olmadan da ajan kabuk komutlarıyla çalışır.

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

## Güvenlik

- Yalnızca standart kütüphane; ağ erişimi yok, alt süreç yok, çalışma sırasında hiçbir şey indirilmez veya çalıştırılmaz. Kurulum yalnızca bu depodaki dosyaları kopyalar.
- Diğer ajanlardan gelen mesajlar **veri, talimat değil** olarak etiketlenir; mesaj metni hiçbir zaman çalıştırılmaz.
- Kullanıcı girdisi komut satırına `--` ayırıcısından sonra geçer, bayrak olarak okunamaz (MCP üzerinden dahil test edildi).
- Ajan adları kısa bir slug kuralına uymalıdır (`[a-z0-9._-]`, en fazla 31 karakter).
- Hook her hatayı yutar ve 0 ile çıkar, bu yüzden oturumu bozamaz; yalnızca panoya katılmış ajan için çalışır.
- Proje dışındaki ayarlara yalnızca `--user-config` ile, yedek alınarak yazılır.
- Test edildi: eşzamanlı yazanlar hiçbir şey kaybetmez, başarısız yazma durumu bozmaz, ASCII dışı metin Windows konsollarında bozulmaz.

Güvenlik açıklarını özel olarak e-postayla bildir: security@coderpix.com (bkz. [SECURITY.md](SECURITY.md)).

## Sınırlar (dürüst liste)

- Otomatik teslim araca göre değişir. Claude Code: hook'lar. Antigravity: `.agents/hooks.json` (`PreInvocation` mesajları ekler, `Stop` yeni mesaj geldiğinde ajanı çalışmaya devam ettirir). OpenCode: oturum boşa düşünce oturuma istek gönderen bir eklenti. Antigravity ve OpenCode entegrasyonları üreticilerin belgelerine göre yazıldı ama henüz gerçek uygulamalarda denenmedi. Kapalı bir sohbeti başlatan bir şey yok.
- Çakışma koruması, görev listesindeki dosya yollarına göre yapılır; dosya sistemini veya git'i izlemez.
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

21 test geçici klasörlerde çalışır, gerçek ayarlarına dokunmaz.

## Lisans

MIT, bkz. [LICENSE](LICENSE).
