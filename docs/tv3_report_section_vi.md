# Phần báo cáo của TV3: Tách/ghép khối và UCS

> Bản nháp để TV5 ghép vào Report.pdf (mục Formalization: phần split, và mục UCS). Số liệu lấy
> từ `docs/experiments/results.csv` (đo lại ngày 28/10 bằng `python tools/benchmark.py`), riêng
> mục 2.3 và 2.4 lấy từ `docs/experiments/bfs_ucs_astar.csv` (31/10, sau khi thêm phụ phí băng).

## 1. Tách và ghép khối

### 1.1 Biểu diễn trạng thái

`GameState` dùng một class cho cả hai chế độ:

| Chế độ | Trường dùng | Trường bỏ trống |
| --- | --- | --- |
| Khối nguyên | `position` (ô neo), `orientation`, `bridge_mask` | `cube_positions = ()`, `active_cube = None` |
| Khối đã tách | `cube_positions` (cặp ô), `active_cube` (0 hoặc 1), `bridge_mask` | `position = orientation = None` |

`__post_init__` cấm trộn trường của hai chế độ và cấm hai cube trùng ô. Cặp `cube_positions`
luôn được **sắp xếp tăng dần**: hai cube giống hệt nhau, nên "cube A ở x, cube B ở y" và
"cube A ở y, cube B ở x" là cùng một trạng thái. Khi phải đảo thứ tự, `active_cube` được đảo theo
để vẫn chỉ đúng cube đang điều khiển. Nhờ vậy số trạng thái tách giảm một nửa và mọi visited set
đều gộp đúng.

`bridge_mask` có mặt ở cả hai chế độ, nên trạng thái tách với cầu mở và với cầu đóng là hai
trạng thái khác nhau.

### 1.2 Công tắc tách

- Khai báo trong JSON: `"split_switches": [{"position": [r, c], "targets": [[r1, c1], [r2, c2]]}]`.
  Ô công tắc và hai ô đích phải là sàn.
- Chỉ **khối nguyên đứng** trên ô công tắc mới kích hoạt. Khối nằm đè lên và cube đơn đều không.
- Khi kích hoạt, khối biến thành hai cube 1×1×1 đặt tại hai ô đích, `active_cube = 0`. Nếu hai ô
  đích kề nhau thì hai cube ghép lại ngay.
- Trong `try_move`, công tắc tách được xét **sau cùng**: lăn → kiểm tra ô đỡ → kích soft/heavy
  switch → kiểm tra lại theo mask mới → công tắc tách.

### 1.3 Hành động khi đã tách

Thứ tự sinh con: Up, Down, Left, Right, Switch.

- **Up/Down/Left/Right** dời cube đang điều khiển 1 ô; cube kia đứng yên.
- **Switch** đổi cube đang điều khiển, không dời cube nào.

Một bước của cube bị loại khi: ra ngoài bàn; đáp lên ô trống hoặc cầu đang đóng; đáp lên ô của
cube kia; hoặc nhấn công tắc làm đóng cầu dưới một trong hai cube (cube đó rơi).

### 1.4 Cube đơn và các ô nâng cao

Cube đơn nhẹ. Engine áp đúng quy ước kích hoạt của TV2, gọi `apply_triggers(..., standing=False)`:

| Ô | Cube đơn |
| --- | --- |
| Sàn, fragile | Đứng được; fragile chỉ vỡ dưới khối nguyên đứng |
| Cầu `1`–`9` | Đứng được khi cầu đang mở theo `bridge_mask` |
| Soft switch | Kích hoạt một lần khi cube đáp lên (toggle, permanent_open, permanent_close) |
| Heavy switch | Không kích hoạt |
| Split switch | Không kích hoạt |
| Goal | Không thắng |

Đây chính là câu "A single cube can activate soft switches but cannot activate heavy switches
or complete the stage" ở mục 2.5 của đề.

### 1.5 Ghép khối

Sau mỗi bước của cube, nếu hai cube kề nhau theo cạnh (khoảng cách Manhattan bằng 1) thì ghép:
cùng hàng thành khối nằm ngang, cùng cột thành khối nằm dọc, neo là ô có tọa độ nhỏ hơn. Khối
ghép giữ `bridge_mask` sinh ra từ chính bước vừa đi (cube có thể vừa nhấn soft switch).

### 1.6 Điều kiện thắng

Chỉ khối nguyên, đứng, neo trùng goal. Trạng thái tách không bao giờ là goal, nên lời giải nào
có tách cũng phải ghép lại trước khi về đích.

## 2. UCS

### 2.1 Thuật toán

```text
frontier = heap [(0, counter, start)]
best_cost[start] = 0; parent[start] = none

while frontier không rỗng:
    (g, _, s) = pop nhỏ nhất
    if g > best_cost[s]: bỏ qua            # bản ghi cũ (stale)
    if is_goal(s): dựng đường từ parent, trả về
    expanded += 1
    for (a, s') in get_successors(s):
        g' = g + cost(s, a, s')            # cost ≥ 0, âm thì báo lỗi
        if g' < best_cost[s']:
            best_cost[s'] = g'; parent[s'] = (s, a)
            push (g', counter, s')
return không có lời giải
```

- `heapq` không có thao tác giảm khóa, nên mỗi lần tìm được đường rẻ hơn thì đẩy một bản ghi mới
  và lọc bản cũ khi lấy ra (lazy deletion).
- `counter` phá thế hòa theo thứ tự FIFO cố định và tránh việc Python phải so sánh hai `GameState`.
- `best_cost` vừa là tập đã thăm vừa giữ chi phí tốt nhất, nên không có vòng lặp.

### 2.2 Tính đúng đắn và độ phức tạp

Mọi chi phí đều dương, nên khi một trạng thái được lấy ra khỏi heap lần đầu với `g = best_cost`
thì `g` là chi phí nhỏ nhất tới nó (lập luận Dijkstra). Vì vậy goal test đặt lúc **lấy ra**: nếu
đặt lúc đưa vào, có thể trả về một đường đắt hơn đường còn nằm trong heap. Với `V` trạng thái tới
được và `E` cạnh, UCS chạy trong O((V + E) log V) và tốn O(V) bộ nhớ.

### 2.3 Hàm chi phí

`default_cost_function` trong `solvers/ucs.py`:

| Bước | Chi phí | Lý do |
| --- | ---: | --- |
| Lăn khối nguyên, bước của cube đơn | 1,0 | Một lần di chuyển thật |
| Switch (đổi cube đang điều khiển) | 0,5 | Không khối nào di chuyển, chỉ đổi quyền điều khiển; vẫn > 0 để UCS không lặp đổi qua đổi lại miễn phí |
| Bước đứng lên split switch và tách | 1,5 | Tách khối là thao tác lớn, phải ghép lại sau đó; chi phí cao khiến UCS chỉ tách khi đường không tách đắt hơn |
| Bước đáp lên ô fragile (khối hoặc cube) | cộng thêm 3,0 | Băng mỏng rủi ro: đứng nhầm là thua cả màn. Mỗi bước chỉ cộng một lần, dù đè lên một hay hai ô băng; cube đang đứng yên trên băng không bị tính |

`--unit-cost` (`unit_cost_function`) đặt mọi bước bằng 1; khi đó UCS cho cùng độ dài lời giải với
BFS trên mọi màn (`tests/test_ucs.py`).

**Vì sao cần phụ phí băng.** Nếu chỉ có hai mức giá liên quan tới tách khối, UCS chọn đúng đường
của BFS trên cả 30 màn giải được: màn không có split switch thì mọi bước tốn 1, còn màn có split
switch thì +0,5 khi tách và −0,5 khi đổi cube thường triệt tiêu nhau. Đó chính là trường hợp đề
bài cảnh báo. Phụ phí băng làm hàm chi phí đo một thứ khác số nước: độ rủi ro của đường đi.

**Chọn mức phụ phí.** Mức 3,0 có nghĩa là UCS chấp nhận đi thêm tối đa 3 nước để tránh một lần đáp
lên băng. Bảng dưới thử nhiều mức trên 30 màn giải được, so với đường của BFS tính trên cùng hàm:

| Phụ phí | Số màn UCS rẻ hơn BFS | Số màn UCS đi nhiều nước hơn BFS | Số nước của UCS ở `advanced/02`, `split/03`, `hard/02`, `demo/08` |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | 6, 31, 37, 23 |
| 0,5 và 1 | 3 | 1 | 6, 32, 37, 23 |
| 1,5 và 2 | 3 | 2 | 6, 33, 37, 27 |
| 2,5; 3; 4; 5 và 10 | 4 | 3 | 8, 33, 37, 27 |

Từ 2,5 trở lên số nước của UCS không đổi nữa, nên kết luận không phụ thuộc vào con số 3,0 cụ thể.
Mức này được chọn sau khi xem bảng trên, để sự khác biệt với BFS hiện rõ; nó không được suy ra từ
một mô hình rủi ro.

Hàm chi phí chỉ đổi kết quả khi có băng trên đường đi: trong 8 màn giải được có băng, UCS đổi
đường ở 5 màn và rẻ hơn BFS thật sự ở 4 màn. Trên 22 màn giải được còn lại, UCS vẫn đi đúng đường
của BFS. Mọi phép lăn vẫn tốn ít nhất 1, nên `relaxed_heuristic` vẫn chấp nhận được khi A\* dùng
chung hàm này (`docs/report_astar_experiments_vi.md`, mục 2.2).

### 2.4 Số liệu trên nhóm split

Số nút mở rộng / độ dài lời giải / tổng chi phí, với đường của BFS được tính trên cùng hàm chi phí:

| Màn | BFS | UCS (chi phí mặc định) |
| --- | --- | --- |
| `01_split_intro` | 6 / 4 / 4,5 | 8 / 4 / 4,5 |
| `02_split_reunion` | 4 857 / 31 / 31 | 4 864 / 31 / 31 |
| `03_fragile_split` | 6 401 / 31 / 49 | 5 356 / 33 / 39 |
| `04_heavy_split_bridges` | 8 002 / 29 / 29 | 8 083 / 29 / 29 |

Ở `01_split_intro`, bốn nước gồm một bước tách 1,5 nên tổng chi phí là 1 + 1,5 + 1 + 1 = 4,5.
Ở `02` và `04`, lời giải có đúng một bước tách (1,5) và một bước Switch (0,5); hai mức lệch triệt
tiêu nhau nên tổng chi phí trùng số nước, và UCS mở rộng nhiều hơn BFS 0,1–1,0 % vì thứ tự lấy ra
theo chi phí khác thứ tự theo số nước. `03_fragile_split` là màn duy nhất của nhóm có băng: UCS đi
thêm 2 nước để giảm số lần đáp lên băng từ 6 xuống 2, tổng chi phí 39 so với 49, và mở rộng ít hơn
BFS 16 % vì trạng thái đã qua băng có chi phí cao nên bị đẩy về sau trong hàng đợi.

### 2.5 Kiểm thử

`tests/test_ucs.py` (15 test): lời giải ngắn nhất, màn vô nghiệm, đứng sẵn ở đích, replay đúng,
unit cost trùng BFS trên mọi màn `basic`, chọn đường rẻ hơn dù dài hơn khi chi phí lệch, đủ các
chỉ số; tám test cho phụ phí băng: giá từng loại bước, cube đứng yên trên băng không bị tính, UCS
đi vòng băng trên `advanced/02`, rẻ hơn với cùng số nước trên `hard/02`, chi phí bằng số nước trên
màn không có băng. `tests/test_split.py` thêm một test duyệt **mọi** chuỗi hành động có độ dài tới số bước
BFS + 2 trên `split/01_split_intro` và xác nhận không chuỗi nào tới đích với chi phí nhỏ hơn
`path_cost` của UCS.

## 3. Kiểm thử phần tách/ghép

`tests/test_split.py` (21 test):

- tách đúng khi đứng trên công tắc; nằm đè không tách; đổi cube; bước của cube và biên bàn; hai
  cube không trùng ô; ghép ngang, ghép dọc; trạng thái tách không thắng; khối nguyên không có
  Switch; BFS và UCS giải trọn một màn có tách và ghép;
- cube với ô nâng cao: đi qua cầu đang mở; rơi xuống cầu đang đóng; nhấn soft switch và toggle lần
  hai thì đóng lại; không nhấn được heavy switch; permanent_open giữ nguyên khi nhấn lại; soft
  switch đóng cầu dưới cube kia thì nước đi bất hợp lệ; đứng được trên fragile; ghép giữ mask mới;
  `bridge_mask` phân biệt hai trạng thái tách cùng vị trí; mọi trạng thái con đều đứng trên cầu
  đang mở.

`tests/test_extra_levels.py` kiểm tra độ dài BFS ghi trong file của các màn `split`, `hard`,
`demo`, và rằng lời giải của `demo/07_split` có một bước cube nhấn soft switch.

## 4. Thay đổi ngày 28/10

Trước ngày này, cube đơn coi mọi cầu là ô trống và không bao giờ nhấn công tắc, trái với mục 2.5
của đề. Bản sửa trong `engine/split.py` (`try_move_split`) dùng `is_cell_supported` và
`apply_triggers(standing=False)` của TV2, rồi kiểm tra lại hai cube theo mask mới. Năm test mới
trong `tests/test_split.py` thất bại trên bản cũ và đạt trên bản mới.

Ảnh hưởng: `split/04_heavy_split_bridges` ngắn lại từ 33 xuống 29 nước (một cube nhấn soft switch
mở cầu 2, không cần khối nguyên quay lại), số nút BFS tăng từ 3 802 lên 8 002 vì cube có thêm
đường đi. Ba màn split còn lại không có cầu hay công tắc nên không đổi. Thêm `demo/07_split` (BFS
18) và đưa công tắc tách trở lại `demo/08_showcase` (BFS 23, trước là 24). Toàn bộ benchmark được
đo lại, và tính chấp nhận được, nhất quán của `relaxed_heuristic` được kiểm lại trên 32 829 trạng
thái của cả 34 màn.
