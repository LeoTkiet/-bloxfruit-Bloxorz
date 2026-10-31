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
- `tests/test_gui.py`, `tests/test_board3d.py`: 25 test cho GUI.

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
- **Game**: chọn một trong 10 màn demo (`DEMO_STAGES` trong `gui/app.py`; màn khác mở bằng
  *Open...*), *New Game* (nạp lại màn từ
  file, xóa kết quả giải), *Restart* (về vị trí xuất phát, giữ kết quả giải), *Open...*,
  *Undo* và bộ đếm nước đi.
- **Solvers**: năm nút *Solve BFS / DFS / IDS / UCS / A\**, chạy ở luồng nền nên giao
  diện không bị treo, luôn giải từ vị trí xuất phát. Không có đường đi thì báo
  *No solution found*.
- **Result**: thuật toán, tìm thấy hay không, độ dài lời giải, tổng chi phí, số nút mở
  rộng, thời gian tìm kiếm, bộ nhớ đỉnh. Chi phí của mọi solver đều tính bằng hàm chi phí của UCS
  (`Backend.step_cost`), nên so được với nhau; BFS, DFS, IDS vẫn chỉ tìm theo số nước.
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
| A\* | `solvers.astar` | `heuristic=split_heuristic` |

Module chưa có thì nút bị khóa và khung Solvers ghi *not merged yet*. Module có nhưng
import lỗi thì chỉ nút đó bị khóa, khung Solvers hiện lỗi, GUI vẫn chạy bình thường.

## Ghi chú cho TV3 và TV4

- **TV3 (split):** GUI đã đọc sẵn `level.split_switches` (cặp `(ô công tắc, (đích 1, đích 2))`),
  `Action.SWITCH` (phím Space) và `is_split` / `cube_positions` / `active_cube`. Hai test
  split trong `tests/test_gui.py` và `tests/test_board3d.py` tự chạy khi `levels/` có màn
  chứa công tắc tách. `GameState` sắp xếp lại `cube_positions` (để hai trạng thái
  giống nhau băm giống nhau), nên phần tử 0 không luôn là cùng một cube. Engine giữ nguyên quy
  ước này; GUI dùng `keep_piece_order` trong `gui/backend.py`: cube không di chuyển giữ nguyên
  vị trí của nó, nên phần đầu và phần chân không đổi chỗ trên màn hình (`app.py` đưa mọi
  trạng thái qua `App._state_view`). Cube đơn đi được trên cầu đang mở và nhấn được công tắc mềm
  (xem `docs/tv3_handoff.md`, mục 2b).
- **TV4 (A\*):** nút A\* truyền `split_heuristic` (`_astar_solver` trong `gui/backend.py`). Với
  khối nguyên, hàm này là `relaxed_heuristic`: số lần lăn ít nhất tới đích trên bàn nới lỏng (mọi
  cầu mở, bỏ luật fragile), coi công tắc tách cũng là đích nên vẫn chấp nhận được trên màn split.
  Với khối đã tách, hàm lấy số bước ít nhất để hai cube đứng kề nhau trên bàn nới lỏng cộng với
  `relaxed_heuristic` của khối sau khi ghép, bỏ qua những chỗ ghép không tới được đích nào. Nút này
  tìm trên hàm chi phí của UCS, nên A\* và UCS cùng mục tiêu và chỉ khác số nút. Lập luận và số đo
  của `relaxed_heuristic` nằm trong `docs/report_astar_experiments_vi.md`. `solve` và lệnh
  `python -m solvers.astar` vẫn mặc định `h = 0` với mỗi nước tốn 1; thêm `--split-heuristic`
  để dùng heuristic này và `--ucs-cost` để dùng hàm chi phí của UCS.

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
| `07_split` | Tách khối; một cube nhấn công tắc mềm mở cầu; ghép lại rồi về đích | 18 |
| `08_showcase` | Mọi loại ô: băng mỏng, công tắc mềm, công tắc nặng, công tắc tách (đường tắt qua băng) | 23 |
| `09_unsolvable` | Khe trống không qua được | vô nghiệm |

`07_split` và công tắc tách của `08_showcase` được thêm lại ngày 28/10, sau khi sửa luật cube
đơn trong `engine/split.py`. Có công tắc tách, `08_showcase` ngắn hơn bản cũ một nước (24 → 23).

## Asset 3D

Quy ước: 1 đơn vị = 1 ô, trục z hướng lên, +x là hướng đông (cột), +y là hướng nam (hàng),
mặt trên của ô ở z = 0. Mỗi model là một khối lồi; các mặt thuộc object có tên chứa
`decal` là họa tiết vẽ phẳng lên mặt khối. Model mở được bằng Blender (import với trục Z
hướng lên) hoặc 3D Viewer của Windows. Nếu sửa model bằng tay thì giữ đúng các quy ước
này; test `test_files_match_generator` báo khi file trên đĩa khác với script sinh.
