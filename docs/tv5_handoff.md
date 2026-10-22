# TV5 Handoff: GUI 3D, phát lại lời giải và tích hợp

## Phạm vi bàn giao

- `main.py`: điểm vào chương trình (`python main.py [file màn]`).
- `gui/`: giao diện Tkinter có bảng chơi 3D tự dựng hình, không dùng thư viện ngoài.
  - `app.py`: cửa sổ chính, chọn màn, chơi tay, nút solver, bảng số đo, replay.
  - `board_view.py`: bảng 3D, hoạt ảnh lăn/tách/rơi/chìm, camera.
  - `render3d.py`: phép chiếu phối cảnh, đổ bóng phẳng, xoay khối quanh cạnh đáy.
  - `models.py`: đọc model `.obj`/`.mtl` trong `assets/models/`.
  - `backend.py`: **điểm nối duy nhất** giữa GUI và `engine/` + `solvers/`.
  - `theme.py`: màu và font.
- `assets/models/`: 11 model `.obj` + `palette.mtl`, sinh bằng `python tools/build_models.py`.
- `levels/demo/`: các màn dùng để quay video demo (xem mục cuối).
- `tests/test_gui.py`, `tests/test_board3d.py`: 21 test cho GUI.

## Giao diện

- **Bảng chơi** (bên trái): khung cảnh 3D phối cảnh, theme One Piece.
  - *Ô:* sàn là đảo cát nổi trên biển (ô trống là biển; rơi xuống là thua), ô dễ vỡ là
    tấm băng mỏng, đích là hố kho báu viền vàng, cầu là tấm ván gỗ. Cầu đóng là khung chấm
    trên mặt nước; cầu mở thì ván trồi lên, cầu đóng lại thì ván chìm xuống.
  - *Khối:* Buggy, khối 1×1×2 có mặt chú hề, mũi đỏ, mũ thuyền trưởng và đôi ủng. Mỗi
    nước đi khối lăn qua cạnh đáy như khối thật, nên mặt và mũ xoay theo.
  - *Tách (trái Bara Bara):* phần đầu và phần chân bay tới hai ô đích rồi đi riêng; phần
    đang điều khiển có mũi tên vàng phía trên; hai phần kề nhau thì ghép lại.
  - *Thắng/thua:* đi sai thì khối lật qua mép đảo và chìm; đứng trên băng mỏng thì băng vỡ;
    thắng thì khối tụt xuống hố kho báu.
  - Rê chuột lên công tắc để thấy các ô cầu nó điều khiển (viền vàng) hoặc hai ô đích khi
    tách (khung tím). Thanh trạng thái mô tả ô đang trỏ và tư thế hiện tại của khối.
- **Game**: chọn màn (`basic/…`, `advanced/…`, `demo/…`), *New Game* (nạp lại màn từ
  file, xóa kết quả giải), *Restart* (về vị trí xuất phát, giữ kết quả giải), *Open...*,
  *Undo* và bộ đếm nước đi.
- **Solvers**: năm nút *Solve BFS / DFS / IDS / UCS / A\**, chạy ở luồng nền nên giao
  diện không bị treo, luôn giải từ vị trí xuất phát. Không có đường đi thì báo
  *No solution found*.
- **Result**: thuật toán, tìm thấy hay không, độ dài lời giải, tổng chi phí, số nút mở
  rộng, thời gian tìm kiếm, bộ nhớ đỉnh.
- **Solution replay**: danh sách nước đi (bấm một dòng để nhảy tới bước đó), các nút
  *Start / Prev / Play / Next / End* và thanh tốc độ. Bấm phím di chuyển giữa lúc replay
  để chơi tiếp từ trạng thái đó.

Phím tắt nằm trong `README.md`, mục *Play (GUI)*.

## Cách GUI dùng engine

GUI không có luật chơi riêng: chơi tay, kiểm tra thắng và replay đều gọi
`engine.get_successors` / `engine.is_goal`. Lời giải của solver được cho engine chạy lại
từng nước trong `moves`, nên một lời giải sai sẽ bị báo *Invalid solution* thay vì được vẽ.

Mọi chỗ đọc dữ liệu của engine nằm trong `gui/backend.py`:

| Hàm | Đọc từ engine | Trả cho bảng 3D |
|---|---|---|
| `level_view(level)` | `width`, `height`, `floor_tiles`, `goal`, `tiles.fragile`, `tiles.bridge_cells`, `tiles.switches` (`kind`, `mode`, `targets`) | lưới loại ô, danh sách ô cầu, công tắc → các ô cầu nó điều khiển |
| `state_view(level, state)` | `orientation`, `occupied_cells(state)`, `is_split`, `cube_positions`, `active_cube`, `tiles.is_bridge_open(cell, bridge_mask)` | tư thế, các ô khối chiếm, cube đang điều khiển, các ô cầu đang mở |
| `stage_description(path)` | khóa `"description"` của file JSON (`Level` không giữ khóa này) | dòng mô tả dưới tên màn |

Nếu engine đổi tên thuộc tính, chỉ cần sửa hai hàm trên; `app.py` và `board_view.py`
không đọc engine trực tiếp.

Các nút solver gọi `solve(level, level.initial_state)` theo hợp đồng chung:

| Nút | Module | Tham số thêm |
|---|---|---|
| BFS | `solvers.bfs` | – |
| DFS | `solvers.dfs` | `strategy="dfs"` |
| IDS | `solvers.dfs` | `strategy="ids"` |
| UCS | `solvers.ucs` | – |
| A\* | `solvers.astar` | – |

Module chưa có thì nút bị khóa và khung Solvers ghi *not merged yet*. Module có nhưng
import lỗi thì chỉ nút đó bị khóa, khung Solvers hiện lỗi, GUI vẫn chạy bình thường.

## Ghi chú cho TV3 và TV4

- **TV3 (split):** GUI đã đọc sẵn `level.split_switches` (cặp `(ô công tắc, (đích 1, đích 2))`),
  `Action.SWITCH` (phím Space) và `is_split` / `cube_positions` / `active_cube`. Hai test
  split trong `tests/test_gui.py` và `tests/test_board3d.py` tự chạy khi `levels/` có màn
  chứa công tắc tách. Lưu ý: `GameState` sắp xếp lại `cube_positions`, nên phần tử 0 không
  luôn là cùng một cube; bảng 3D vẽ phần tử 0 là phần đầu, nên khi hai cube đổi thứ tự thì
  đầu và chân có thể đổi chỗ trên màn hình. Cần thống nhất cách giữ thứ tự cube khi merge.
- **TV4 (A\*):** GUI gọi `solve(level, initial_state)` không truyền heuristic, nên
  `solve` cần tự chọn heuristic (ví dụ hình học khi màn không có công tắc tách, `h = 0` khi
  có), nếu không nút A\* sẽ chạy như UCS chi phí đơn vị.

## Màn demo (`levels/demo/`)

Chuyển từ định dạng nháp ngày 1–3 của TV5 sang định dạng chung (`grid`, cầu `1`–`9`,
`switches` với `mode`/`targets`). Số nước BFS khớp với bản nháp trên cả 5 màn không đổi
nội dung.

| Màn | Nội dung | BFS |
|---|---|---|
| `03_classic_stage1` | Màn 1 của Bloxorz gốc | 7 |
| `04_fragile` | Băng mỏng: phải nằm để đi qua | 18 |
| `05_soft_switch_bridge` | Công tắc mềm mở cầu | 7 |
| `06_heavy_switch` | Công tắc nặng mở cầu vĩnh viễn | 18 |
| `08_showcase` | Băng mỏng + công tắc mềm + công tắc nặng | 24 |
| `09_unsolvable` | Khe trống không qua được | vô nghiệm |

`08_showcase` tạm bỏ công tắc tách và màn `07_split` chưa được chuyển; hai màn này sẽ
thêm lại khi phần split của TV3 được merge.

## Asset 3D

Quy ước: 1 đơn vị = 1 ô, trục z hướng lên, +x là hướng đông (cột), +y là hướng nam (hàng),
mặt trên của ô ở z = 0. Mỗi model là một khối lồi; các mặt thuộc object có tên chứa
`decal` là họa tiết vẽ phẳng lên mặt khối. Model mở được bằng Blender (import với trục Z
hướng lên) hoặc 3D Viewer của Windows. Nếu sửa model bằng tay thì giữ đúng các quy ước
này; test `test_files_match_generator` báo khi file trên đĩa khác với script sinh.
