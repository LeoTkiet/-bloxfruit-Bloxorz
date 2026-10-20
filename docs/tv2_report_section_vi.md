# Phần báo cáo của TV2: Cơ chế nâng cao và DFS/IDS

> Bản nháp để TV5 ghép vào Report.pdf. Số liệu trong bảng lấy từ các màn ở
> `levels/advanced/`; TV4 có thể thay bằng số đo chính thức từ khung thực nghiệm.

## 1. Cơ chế nâng cao

### 1.1 Biểu diễn trạng thái

Trạng thái `GameState` là bất biến và băm được, gồm vị trí neo, tư thế
(standing / horizontal / vertical) và **bridge mask** (số nguyên, bit *n−1*
bằng 1 khi cầu *n* đang mở). Vì mask nằm trong trạng thái nên hai trạng thái
cùng vị trí và tư thế nhưng khác cấu hình cầu là **hai trạng thái khác nhau**,
và mọi tập visited của BFS/DFS/IDS/UCS/A\* đều không gộp nhầm chúng.

Công thức: `state = (position, orientation, bridge_mask)`; số cầu tối đa là 9.

### 1.2 Các loại ô

| Ô | Ký hiệu | Quy tắc |
| --- | --- | --- |
| Fragile | `F` | Khối **nằm** (ngang/dọc) đi qua được; khối **đứng** lên ô này thì sập, nước đi bất hợp lệ |
| Cầu | `1`–`9` | Là sàn khi bit tương ứng bằng 1 (mở), là ô trống khi bằng 0 (đóng) |
| Soft switch | `o` | Kích hoạt khi **bất kỳ** phần nào của khối chạm vào |
| Heavy switch | `x` | Chỉ kích hoạt khi khối **đứng** trên ô |

Mỗi công tắc có danh sách cầu đích và một chế độ:

- `toggle`: đảo trạng thái các cầu đích ở mỗi lần kích hoạt;
- `permanent_open`: mở cầu đích và không bao giờ đóng lại;
- `permanent_close`: đóng cầu đích và không bao giờ mở lại.

### 1.3 Hàm chuyển trạng thái

Với mỗi hành động trong thứ tự Up, Down, Left, Right, engine thực hiện:

1. Lăn khối theo bảng 12 chuyển tư thế của TV1 để có các ô mới.
2. Kiểm tra mọi ô mới nằm trong bảng và là sàn hoặc cầu đang mở theo mask
   **trước** nước đi; khối đứng trên ô fragile bị loại.
3. Kích hoạt các công tắc mà vị trí vừa đáp chạm vào, cập nhật mask.
4. Kiểm tra lại các ô đang đứng theo mask **mới**. Nếu công tắc vừa đóng cầu
   ngay dưới khối thì khối rơi và nước đi bị loại.

Chi phí mỗi nước đi vẫn bằng 1.

### 1.4 Quy ước kích hoạt công tắc (tránh bật/tắt lặp)

Công tắc chỉ kích hoạt **một lần cho mỗi nước đi**, tại vị trí khối vừa đáp, không
kích hoạt theo thời gian hay khi khối đứng yên. Điều này đúng đắn vì một phép lăn
không bao giờ giữ lại ô nào đã chiếm trước đó, nên cùng một vị trí không thể
chạm công tắc hai lần liên tiếp. Nếu một khối nằm đè lên hai công tắc cùng lúc,
chúng kích hoạt theo thứ tự hàng rồi cột; khi tác dụng mâu thuẫn (một mở, một đóng)
thì công tắc sau thắng. Khối đơn của TV3 chỉ gọi với `standing=False` nên chỉ
kích hoạt được soft switch.

### 1.5 Kiểm thử

Mỗi loại ô/công tắc có ít nhất một ca hợp lệ và một ca không hợp lệ
(`tests/test_tiles.py`): khối nằm/đứng trên fragile; cầu đóng là ô trống, cầu mở
đi qua được, bit cầu độc lập; soft và heavy trên cùng một vị trí; toggle hai lần
trở lại ban đầu; permanent_open/close không đảo ngược; cầu bị đóng ngay dưới khối
làm khối rơi. Bộ test còn kiểm tra bộ nạp màn (`test_advanced_loader.py`), chín
màn nâng cao so với BFS (`test_advanced_levels.py`) và kiểm tra đột biến: phá từng
quy tắc (heavy như soft, bỏ fragile, bỏ kiểm tra sau kích hoạt, toggle thành mở…)
đều làm ít nhất một test thất bại.

## 2. DFS và IDS

### 2.1 DFS

DFS mở rộng nút sâu nhất trước, dùng **ngăn xếp tường minh** gồm các bộ lặp
successor (không đệ quy nên không vướng giới hạn đệ quy; có test với lời giải
dài 1400 bước). Tập `visited` chứa **toàn bộ** `GameState` (gồm bridge mask) để
chống vòng lặp. Ngăn xếp hiện tại chính là đường đi nên không cần bảng cha.

```text
visited = {start}; stack = [iter(successors(start))]
while stack:
    lấy successor chưa thăm kế tiếp của nút trên cùng
    nếu là goal: trả về đường đi hiện tại
    thêm vào visited; đẩy iterator successor của nó
    nếu hết successor: pop
không tìm được: found = False
```

Tính chất: đầy đủ trên không gian trạng thái hữu hạn, **không tối ưu** (ví dụ màn
`02_fragile_band` DFS ra 34 bước trong khi tối ưu là 6). Bộ nhớ O(độ sâu) cho
ngăn xếp cộng với tập visited.

### 2.2 IDS

IDS chạy lặp DFS giới hạn độ sâu với giới hạn 0, 1, 2, ... Trong mỗi vòng, bảng
`best_depth[state]` ghi độ sâu nông nhất đã đến trạng thái đó; trạng thái chỉ
được mở lại nếu lần này nông hơn. Cách này loại vòng lặp mà vẫn giữ tính đầy đủ
cho giới hạn hiện tại. Khi chi phí mỗi bước bằng 1, vòng đầu tiên chạm goal cho
lời giải ngắn nhất, giống BFS nhưng ngăn xếp chỉ sâu bằng độ dài lời giải. Nếu một
vòng không có nút không-phải-goal nào nằm đúng ở giới hạn độ sâu thì toàn bộ đồ
thị khả đạt đã được duyệt, IDS kết luận vô nghiệm và dừng, nên các màn không giải
được không gây treo.

### 2.3 Cách đo bốn chỉ số

- Thời gian tìm kiếm: `perf_counter` quanh toàn bộ tìm kiếm và dựng đường đi.
- Bộ nhớ đỉnh: `tracemalloc` (phần tăng thêm so với lúc bắt đầu).
- Số nút mở rộng: số trạng thái không phải goal mà successor được sinh ra; với
  IDS cộng dồn qua mọi vòng lặp (nên lớn hơn BFS).
- Độ dài lời giải: số hành động; kèm `path_cost` là tổng chi phí các bước.

### 2.4 Kết quả mẫu và nhận xét

Mỗi ô là *số nút mở rộng / độ dài lời giải*:

| Màn | BFS | DFS | IDS |
| --- | --- | --- | --- |
| 01 fragile corridor | 4 / 4 | 4 / 4 | 10 / 4 |
| 02 fragile band | 50 / 6 | 47 / 34 | 85 / 6 |
| 03 soft switch bridge | 6 / 4 | 6 / 4 | 13 / 4 |
| 04 heavy switch bridge | 79 / 10 | 26 / 23 | 299 / 10 |
| 05 toggle two bridges | 7 / 6 | 7 / 6 | 21 / 6 |
| 06 permanent return | 6 / 6 | 6 / 6 | 21 / 6 |
| 07 advanced mix | 106 / 13 | 111 / 81 | 262 / 13 |
| 08, 09 vô nghiệm | không có | không có | không có |

- **DFS** thường mở rộng ít nút nhất khi gặp may, nhưng lời giải có thể dài hơn
  rất nhiều (81 so với 13 ở màn 07), vì vậy không thích hợp khi cần đường đi ngắn.
- **IDS** cho lời giải ngắn nhất như BFS với bộ nhớ ngăn xếp nhỏ, đổi lại phải
  mở rộng lại các nút nông ở mỗi vòng nên số nút mở rộng nhiều hơn BFS khoảng
  1,7–3,8 lần trên các màn có lời giải ở trên.
- **BFS** tối ưu và mở rộng ít nút hơn IDS, nhưng phải giữ cả biên tìm kiếm trong
  bộ nhớ.

Lưu ý: IDS chỉ tối ưu theo **số nước đi**. Khi chi phí bước không đều (UCS/A\*
của TV3, TV4), phải dùng chi phí đường đi thay vì độ sâu.
