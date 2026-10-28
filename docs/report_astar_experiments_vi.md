# Phần báo cáo: Heuristic A\* và thực nghiệm

> Bản nháp để ghép vào Report.pdf (mục 3.5 A\* và mục Experiments). Mọi số liệu lấy từ
> `docs/experiments/results.csv`, sinh lại được bằng `python tools/benchmark.py`. Biểu đồ
> tương tác: https://claude.ai/artifact/Wb94bZ2wbgu8ce6jRotYme (chụp lại để đưa vào PDF).
> Đo lại toàn bộ ngày 28/10 sau khi sửa luật cube đơn (`split/04`: 33 → 29 nước), thêm
> `demo/07_split` và công tắc tách của `demo/08_showcase`. Biểu đồ trên vẫn dùng số đo ngày
> 26/10, cần dựng lại từ CSV mới.

## 1. Bài toán tìm kiếm

- **Trạng thái:** `(vị trí neo, tư thế, bridge_mask)` khi khối nguyên; `(hai ô cube, cube đang
  điều khiển, bridge_mask)` khi khối đã tách. Hai trạng thái cùng chỗ đứng nhưng khác cấu
  hình cầu là hai trạng thái khác nhau.
- **Hành động:** Up, Down, Left, Right; thêm Switch (đổi cube) khi khối đã tách.
- **Mô hình chuyển:** lăn theo bảng chuyển tư thế, kiểm tra ô đỡ (sàn hoặc cầu đang mở,
  không đứng trên fragile), kích hoạt công tắc tại vị trí đáp, kiểm tra lại theo mask mới;
  đứng trên split switch thì khối tách thành hai cube đặt tại hai ô đích. Cube đơn đi trên sàn,
  fragile và cầu đang mở, nhấn soft switch nhưng không nhấn heavy/split switch.
- **Đích:** khối nguyên **đứng** trên ô goal.
- **Chi phí:** mỗi nước đi tốn 1 (BFS, DFS/IDS, A\*). UCS dùng hàm chi phí của TV3: lăn 1,0,
  đổi cube 0,5, kích split switch 1,5.

## 2. Ba heuristic được so sánh

Ký hiệu `d(s)` là khoảng cách Manhattan từ ô neo của khối tới ô goal.

| Tên | Công thức | Dùng ở đâu |
| --- | --- | --- |
| `h0` (`zero_heuristic`) | `h = 0` | mặc định của `solve`; A\* lúc này chính là UCS chi phí đơn vị |
| `hG` (`astar_heuristic`, TV4) | `h = ⌈d(s) / 2⌉`, bằng 0 khi khối đã tách | chỉ màn không có split switch |
| `hR` (`relaxed_heuristic`, mới) | số lần lăn ít nhất tới đích trên **bàn nới lỏng** | mọi màn; nút A\* trong GUI |

### 2.1 Heuristic hình học `hG` của TV4

Một lần lăn dời ô neo nhiều nhất 2 ô (ví dụ đứng → nằm ngang khi lăn sang trái), nên cần ít
nhất `⌈d/2⌉` lần lăn để neo trùng goal: `hG` **chấp nhận được** khi mỗi lần lăn tốn ≥ 1.
Sau một lần lăn `d` đổi tối đa 2 nên `⌈d/2⌉` đổi tối đa 1, suy ra `hG` **nhất quán**.

Hạn chế:

1. **Không biết tư thế.** Khối nằm đè lên goal có `hG = 0` dù còn ít nhất 1 nước (thực tế
   thường là 3–4 nước) mới dựng đứng được.
2. **Không biết ô trống.** Trên màn có tường void phải đi vòng, `hG` gần như không dẫn đường:
   trên `hard/01_grand_maze` A\* với `hG` mở rộng 396 nút, gần bằng BFS (402).
3. **Không chấp nhận được trên màn split.** Split switch dịch chuyển cube tức thời, nên
   chi phí thật có thể nhỏ hơn `⌈d/2⌉`. Vì vậy GUI cũ phải tắt `hG` (dùng `h0`) trên mọi màn
   có split switch.

### 2.2 Heuristic bàn nới lỏng `hR`

**Bài toán nới lỏng P′.** Giữ nguyên bàn cờ, ô trống và luật lăn, nhưng:

- **mọi cầu luôn mở** (ô cầu được coi là sàn), nên công tắc không còn tác dụng;
- **bỏ luật fragile** (được đứng trên ô fragile);
- **đích** là goal hoặc bất kỳ split switch nào, với khối đứng.

`hR(s)` là số lần lăn ít nhất trong P′ từ chỗ đặt của `s` tới một đích; `hR = 0` khi khối đã
tách. Vì mỗi phép lăn có phép lăn ngược (đứng → nằm bằng Right thì Left đưa về như cũ), đồ thị
của P′ là vô hướng: chỉ cần **một lần BFS** xuất phát từ các đích là có bảng `hR` cho mọi chỗ
đặt (tối đa 3·W·H mục). Bảng tính một lần cho mỗi màn, ở lần gọi đầu tiên, và thời gian đó
được tính vào thời gian tìm kiếm của A\*. Chỗ đặt không tới được đích nào trong P′ cũng không
tới được goal thật, nên được gán 0.

**Chấp nhận được** (mỗi lần lăn tốn ≥ 1). Xét lời giải thật bất kỳ từ trạng thái khối
nguyên `s`. Cắt lời giải tại lần đầu tiên khối đứng trên goal hoặc trên một split switch (lời
giải nào cũng phải tới một trong hai: hoặc về đích mà không tách, hoặc tách, mà tách thì phải
đứng trên split switch). Mọi bước trong đoạn cắt đều là phép lăn của khối nguyên, và mỗi phép
lăn hợp lệ trên bàn thật cũng hợp lệ trong P′: ô sàn và cầu đang mở là tập con của ô đỡ trong
P′, còn luật fragile đã bị bỏ. Vậy đoạn cắt là một đường đi trong P′ tới một đích, dài ít nhất
`hR(s)`, nên chi phí thật ≥ `hR(s)`. Với trạng thái đã tách, `hR = 0` hiển nhiên chấp nhận được.

**Nhất quán**, tức `hR(s) ≤ c(s, s′) + hR(s′)` cho mọi bước `s → s′`:

- lăn giữa hai trạng thái khối nguyên: `s` và `s′` kề nhau trong P′, mà `hR` là khoảng cách
  BFS nên `hR(s) ≤ 1 + hR(s′) ≤ c + hR(s′)`;
- lăn lên split switch rồi tách: `s` cách một đích đúng 1 lần lăn nên `hR(s) ≤ 1 ≤ c + 0`;
- bước giữa hai trạng thái đã tách, hoặc nhập lại thành khối: vế trái bằng 0.

**Trội hơn `hG`.** Trên màn không có split switch, P′ còn chặt hơn bài toán "bàn vô hạn không
có ô trống", mà trên bàn vô hạn số lần lăn đã ≥ `⌈d/2⌉`. Vậy `hR(s) ≥ hG(s)` với mọi `s` còn
tới được goal, và
A\* với `hR` không bao giờ phải mở rộng nút nào mà A\* với `hG` bỏ qua được (trừ khác biệt do
phá thế hòa).

**Với hàm chi phí của UCS:** phép lăn tốn 1,0, kích split switch tốn 1,5 (≥ 1), còn đổi cube
0,5 chỉ xảy ra khi khối đã tách, lúc đó `hR = 0`. Vì vậy `hR` vẫn chấp nhận được và nhất quán
khi A\* dùng hàm chi phí của TV3.

### 2.3 Kiểm chứng bằng máy

Ngoài lập luận trên, `tests/test_astar.py` duyệt **toàn bộ** trạng thái đến được của các màn
(trừ ba màn split lớn) và so `hR` với chi phí thật tới đích, tính bằng BFS ngược:

- không trạng thái nào có `hR` lớn hơn chi phí thật (chấp nhận được);
- không cạnh nào vi phạm `hR(s) ≤ c + hR(s′)` (nhất quán);
- `hR ≥ hG` trên mọi trạng thái tới được đích của màn không có split switch;
- A\* với `hR` cho lời giải dài bằng BFS trên cả 34 màn.

Lần kiểm tra thủ công ngày 28/10 trên cả 34 màn (gồm ba màn split lớn, tổng 32 829 trạng
thái tới được, theo luật cube đơn mới) cũng cho 0 vi phạm cả ba tính chất.

## 3. Thực nghiệm

### 3.1 Bộ test cố định

Mọi thuật toán chạy trên cùng các file trong `levels/`, chia theo độ khó tăng dần:

| Nhóm | Số màn | Nội dung | Kích thước | Số bước tối ưu |
| --- | ---: | --- | --- | --- |
| `basic` | 10 | chỉ sàn, ô trống, goal (1 màn vô nghiệm) | 1×4 – 6×6 | 2 – 6 |
| `advanced` | 9 | fragile; soft/heavy switch; toggle và permanent (2 màn vô nghiệm) | tới 10×5 | 4 – 13 |
| `split` | 4 | split switch, tách và nhập lại; kết hợp fragile, heavy, soft và cầu | tới 20×7 | 4 – 31 |
| `hard` | 4 | bàn lớn: mê cung, dải fragile, mạng 4 cầu / 3 công tắc, màn tổng hợp | 16×11 – 20×12 | 35 – 46 |

Bảy màn `levels/demo/` dùng để quay video; số đo của chúng vẫn có trong CSV nhưng không
đưa vào các bảng tổng hợp vì trùng ý tưởng với `basic`/`advanced`.

### 3.2 Cách đo

- Máy: Intel Core i5-1135G7, 16 GB RAM, Windows 11, Python 3.12.10, một luồng.
- **Thời gian:** `perf_counter` quanh vòng tìm kiếm; lấy trung vị của 3 lần chạy (lần chạy
  > 2 giây chỉ chạy 1 lần). **Bộ nhớ:** đỉnh `tracemalloc` trong lúc tìm kiếm.
  **Nút mở rộng:** số trạng thái được lấy ra và sinh con. **Độ dài lời giải:** số nước đi.
- Hàm chi phí: đơn vị cho BFS, DFS/IDS, A\*; hàm chi phí mặc định của TV3 cho UCS.
- A\* chạy với ba heuristic `h0`, `hG`, `hR`; `hG` bỏ qua trên màn split vì không chấp nhận được.
- Lệnh tái tạo: `python tools/benchmark.py` → `docs/experiments/results.csv` (232 dòng).
- Số đo ngày 28/10 chạy một lượt khi máy chạy chậm hơn lần đo 26/10 (khoảng 1,5 lần ở đa số
  màn). Chạy lại cùng một màn, thời gian dao động tới khoảng ±50 %, nên chỉ so sánh thời gian
  khi chênh lệch lớn. Số nút mở rộng và độ dài lời giải không phụ thuộc máy.

### 3.3 Kết quả tổng hợp theo nhóm

**Tổng số nút mở rộng**

| Nhóm | BFS | DFS | IDS | UCS | A\* h0 | A\* hG | A\* hR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 176 | 191 | 224 | 176 | 176 | 104 | 48 |
| advanced | 264 | 213 | 724 | 264 | 264 | 188 | 97 |
| split | 19 266 | 5 943 | 484 016 | 19 432 | 19 266 | – | 19 089 |
| hard | 3 520 | 3 031 | 608 613 | 3 520 | 3 520 | 2 844 | 1 812 |

**Tổng thời gian tìm kiếm (ms)**

| Nhóm | BFS | DFS | IDS | UCS | A\* h0 | A\* hG | A\* hR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 15.4 | 16.2 | 21.7 | 16.2 | 18.3 | 9.85 | 7.33 |
| advanced | 28.6 | 21.2 | 71.8 | 29.2 | 30.3 | 20.0 | 14.1 |
| split | 3 781 | 1 362 | 111 345 | 5 427 | 5 371 | – | 5 122 |
| hard | 441 | 406 | 97 840 | 511 | 509 | 358 | 237 |

**Bộ nhớ đỉnh lớn nhất trong nhóm (KiB)**

| Nhóm | BFS | DFS | IDS | UCS | A\* h0 | A\* hG | A\* hR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 16.4 | 30.7 | 8.50 | 11.3 | 11.6 | 9.70 | 15.0 |
| advanced | 18.9 | 45.3 | 15.9 | 21.7 | 22.7 | 18.5 | 12.1 |
| split | 1 732 | 2 819 | 1 529 | 2 603 | 2 263 | – | 2 272 |
| hard | 254 | 690 | 219 | 352 | 357 | 205 | 211 |

**Tổng độ dài lời giải (các màn giải được)**

| Nhóm | BFS | DFS | IDS | UCS | A\* h0 | A\* hG | A\* hR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic | 35 | 140 | 35 | 35 | 35 | 35 | 35 |
| advanced | 49 | 158 | 49 | 49 | 49 | 49 | 49 |
| split | 95 | 2 110 | 95 | 95 | 95 | – | 95 |
| hard | 163 | 1 485 | 163 | 163 | 163 | 163 | 163 |

**Chi tiết nhóm `split`: số nút mở rộng / độ dài lời giải / thời gian (ms)**

| Màn | BFS | DFS | IDS | UCS | A\* h0 | A\* hG | A\* hR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01_split_intro | 6 / 4 / 0.47 | 5 / 4 / 0.41 | 10 / 4 / 0.70 | 8 / 4 / 0.91 | 6 / 4 / 0.51 | – | 7 / 4 / 0.66 |
| 02_split_reunion | 4 857 / 31 / 366 | 1 984 / 1629 / 164 | 107 147 / 31 / 22 307 | 4 864 / 31 / 1 255 | 4 857 / 31 / 1 332 | – | 4 873 / 31 / 1 233 |
| 03_fragile_split | 6 401 / 31 / 1 640 | 244 / 223 / 69.4 | 108 653 / 31 / 23 096 | 6 477 / 31 / 1 669 | 6 401 / 31 / 1 707 | – | 6 337 / 31 / 1 713 |
| 04_heavy_split_bridges | 8 002 / 29 / 1 774 | 3 710 / 254 / 1 128 | 268 206 / 29 / 65 941 | 8 083 / 29 / 2 502 | 8 002 / 29 / 2 332 | – | 7 872 / 29 / 2 176 |

**Chi tiết nhóm `hard`: số nút mở rộng / độ dài lời giải / thời gian (ms)**

| Màn | BFS | DFS | IDS | UCS | A\* h0 | A\* hG | A\* hR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01_grand_maze | 402 / 35 / 94.8 | 369 / 126 / 100 | 42 525 / 35 / 10 488 | 402 / 35 / 117 | 402 / 35 / 120 | 396 / 35 / 55.2 | 43 / 35 / 6.11 |
| 02_fragile_bands | 361 / 37 / 34.1 | 288 / 181 / 28.7 | 19 757 / 37 / 2 376 | 361 / 37 / 42.0 | 361 / 37 / 47.9 | 300 / 37 / 38.7 | 207 / 37 / 25.5 |
| 03_switch_network | 1 477 / 45 / 163 | 1 454 / 701 / 169 | 268 560 / 45 / 55 278 | 1 477 / 45 / 197 | 1 477 / 45 / 191 | 1 132 / 45 / 147 | 763 / 45 / 101 |
| 04_grand_finale | 1 280 / 46 / 149 | 920 / 477 / 109 | 277 771 / 46 / 29 698 | 1 280 / 46 / 155 | 1 280 / 46 / 150 | 1 016 / 46 / 117 | 799 / 46 / 105 |

**So sánh heuristic: số nút A\* mở rộng (màn giải được, độ dài tối ưu ≥ 4)**

| Màn | Bước tối ưu | h0 | hG | hR | hR giảm so với hG |
| --- | ---: | ---: | ---: | ---: | ---: |
| basic/05_open_corner | 4 | 15 | 11 | 7 | 36 % |
| basic/06_orientation_loop | 6 | 61 | 42 | 11 | 74 % |
| basic/07_wide_corner | 4 | 33 | 11 | 4 | 64 % |
| basic/08_void_detour | 5 | 21 | 14 | 9 | 36 % |
| basic/09_reverse_corner | 4 | 33 | 13 | 4 | 69 % |
| advanced/02_fragile_band | 6 | 50 | 26 | 11 | 58 % |
| advanced/04_heavy_switch_bridge | 10 | 79 | 71 | 35 | 51 % |
| advanced/07_advanced_mix | 13 | 106 | 65 | 25 | 62 % |
| split/02_split_reunion | 31 | 4 857 | – | 4 873 | – |
| split/03_fragile_split | 31 | 6 401 | – | 6 337 | – |
| split/04_heavy_split_bridges | 29 | 8 002 | – | 7 872 | – |
| hard/01_grand_maze | 35 | 402 | 396 | 43 | 89 % |
| hard/02_fragile_bands | 37 | 361 | 300 | 207 | 31 % |
| hard/03_switch_network | 45 | 1 477 | 1 132 | 763 | 33 % |
| hard/04_grand_finale | 46 | 1 280 | 1 016 | 799 | 21 % |
| demo/03_classic_stage1 | 7 | 64 | 26 | 14 | 46 % |
| demo/04_fragile | 18 | 61 | 61 | 47 | 23 % |
| demo/05_soft_switch_bridge | 7 | 35 | 13 | 11 | 15 % |
| demo/06_heavy_switch | 18 | 80 | 62 | 30 | 52 % |
| demo/07_split | 18 | 514 | – | 531 | – |
| demo/08_showcase | 23 | 943 | – | 908 | – |

## 4. Nhận xét

**Tính tối ưu.** BFS, IDS, UCS và A\* với cả ba heuristic đều cho lời giải ngắn nhất trên mọi
màn. DFS thì không: ở nhóm `hard` tổng độ dài lời giải của DFS là 1 485 nước so với 163 nước
tối ưu (gấp khoảng 9 lần), ở nhóm `split` là 2 110 so với 95, riêng `split/02_split_reunion`
DFS đi 1 629 nước cho bài toán chỉ cần 31. DFS đôi khi mở rộng ít nút hơn BFS (244 so với 6 401
ở `split/03_fragile_split`) vì nó lao sâu và chạm đích sớm, nhưng đường tìm được không dùng được.

**IDS** tối ưu như BFS và có bộ nhớ đỉnh thấp nhất trong bốn thuật toán không dùng heuristic
(BFS, DFS, IDS, UCS) ở mọi nhóm, nhưng phải lặp lại cả cây ở mỗi
độ sâu: nhóm `hard` mở rộng 608 613 nút (gấp khoảng 170 lần BFS) và mất khoảng 98 giây so với
0,44 giây của BFS. Trên các bàn Bloxorz nhỏ như ở đây, BFS hiếm khi hết bộ nhớ, nên lợi thế bộ
nhớ của IDS không đáng với thời gian tăng thêm.

**UCS** cho đúng số nút và độ dài như BFS ở `basic`, `advanced`, `hard`, vì hàm chi phí hiện tại
chỉ khác 1 ở các bước liên quan tới tách khối (đổi cube 0,5, kích split switch 1,5); mọi phép
lăn đều tốn 1,0 nên UCS suy biến thành BFS, đúng như đề bài cảnh báo. Do dùng hàng đợi ưu tiên,
tổng thời gian của UCS cao hơn BFS 2–16 % ở ba nhóm không tách và 44 % ở nhóm `split`; bộ nhớ
đỉnh cao hơn 15–50 % ở `advanced`, `split`, `hard`. Muốn UCS có ý nghĩa ở các màn không
tách, cần thêm chi phí khác 1 cho phép lăn, ví dụ lăn lên ô fragile đắt hơn (bản đầu của
`docs/tv3_handoff.md` có ghi 1,5 nhưng `solvers/ucs.py` chưa bao giờ cài; tài liệu đã sửa cho
khớp code).

**A\* và heuristic.**

- `h0` cho kết quả trùng UCS chi phí đơn vị, vì vậy nút A\* cũ trong GUI (chạy `h0`) không
  khác BFS.
- `hG` của TV4 giảm 0–67 % số nút so với `h0`, nhưng gần như vô dụng trên mê cung có nhiều
  ô trống: `hard/01_grand_maze` 396 nút so với 402 của BFS.
- `hR` giảm tiếp 15–89 % so với `hG` trên mọi màn không tách mà A\* phải mở rộng từ 10 nút trở
  lên (các màn nhỏ hơn thì ba heuristic như nhau). Tổng nhóm `hard`:
  3 520 (BFS) → 2 844 (`hG`) → 1 812 (`hR`), tức ít hơn BFS 49 %. Tổng nhóm `basic`:
  176 → 104 → 48. `hard/01_grand_maze` giảm mạnh nhất (402 → 43 nút, 95 ms → 6 ms) vì bàn
  nới lỏng vẫn giữ ô trống, nên `hR` biết đường vòng của mê cung. `hard/04_grand_finale` giảm ít
  hơn (21 %) vì phần khó nằm ở thứ tự bấm công tắc, thứ mà `hR` cố ý bỏ qua.
- Thời gian không giảm theo đúng tỉ lệ số nút: mỗi nút A\* tốn thêm thao tác heap và tra
  bảng, cộng chi phí dựng bảng `hR` một lần cho mỗi màn. Trên `hard/04` A\* `hR` mở rộng ít hơn
  BFS 38 % nhưng thời gian chỉ giảm khoảng 30 % (105 ms so với 149 ms; lần đo 26/10 hai số này
  ngang nhau). Trên màn rất nhỏ, bảng `hR` làm bộ
  nhớ đỉnh nhích lên vài KiB.

**Màn split làm không gian trạng thái bùng nổ.** Sau khi tách, trạng thái là một *cặp* vị trí
cube, nên bàn 12×8 của `split/02_split_reunion` đã có gần 5 000 trạng thái, nhiều hơn bàn 20×12
của `hard/04`. Heuristic giúp rất ít ở nhóm này: `hR` bớt tối đa 1,6 % (`split/04`), còn ở
`split/02` lại mở rộng nhiều hơn `h0` 0,3 % do cách phá thế hòa. Lý do là phần lớn trạng thái
là trạng thái đã tách, nơi `hR = 0`. Một heuristic chấp nhận được cho trạng thái đã tách (ví dụ
dựa trên số bước để hai cube kề nhau rồi khoảng cách `hR` từ chỗ nhập) là hướng cải thiện tiếp.

## 5. Thay đổi trong mã nguồn

- `solvers/astar.py`: thêm `relaxed_heuristic` (cùng bảng khoảng cách lưu đệm theo màn) và cờ
  `--relaxed-heuristic` cho lệnh `python -m solvers.astar`. `solve` vẫn mặc định `h0` để giữ
  hợp đồng cũ; `astar_heuristic` của TV4 giữ nguyên để so sánh.
- `gui/backend.py`: nút A\* truyền `relaxed_heuristic` trên mọi màn (trước đây là `h0`).
- `tools/benchmark.py`: khung thực nghiệm chạy 7 cấu hình solver trên mọi màn, ghi CSV.
- `tests/test_astar.py`, `tests/test_gui.py`: kiểm tra `hR` chấp nhận được, nhất quán, trội hơn
  `hG`, và A\* `hR` cho lời giải tối ưu trên cả 34 màn.
