# Phụ lục: Sử dụng AI tạo sinh trong phần việc của TV5

**Công cụ:** Claude Code (Anthropic), chạy trong VS Code.
**Thời gian:** 16/10/2026 đến 30/10/2026.
**Phạm vi:** chỉ gồm các phiên làm việc của Nguyên (TV5). Các thành viên khác bổ sung phần của mình nếu có dùng AI.

Prompt được trích gần nguyên văn, chỉ sửa lỗi gõ và rút gọn phần không liên quan. Số liệu là số đo tại thời điểm thực hiện, nên số liệu chính thức lấy theo mục Experiments của báo cáo.

## Tóm tắt

| # | Nhóm việc | AI đã làm | Cách kiểm chứng chính |
|---|---|---|---|
| 1 | Đọc đề, tách việc | Chuyển tài liệu sang Markdown, trích nhiệm vụ TV5 | So từ ngữ với file gốc |
| 2 | Khảo sát repo mẫu | So sánh GUI của 5 repo | Đọc mã nguồn từng repo |
| 3 | Xây dựng GUI | Viết GUI, theme One Piece, bộ dựng hình 3D | Test tự động, chạy GUI và chụp màn hình |
| 4 | Ghép với core nhóm | Tìm điểm lệch, sửa GUI theo core chung | Chạy test của nhóm cùng test GUI |
| 5 | Màn chơi | Thêm màn, phân tích độ phủ, đề xuất bộ demo | Chạy cả 4 solver trên từng màn mới |
| 6 | Heuristic cho A\* | Viết `relaxed_heuristic`, `split_heuristic` | Thử trên bản clone, so số nút mở rộng |
| 7 | Chi phí UCS | Giải thích và chỉnh hàm chi phí | Đo BFS, UCS, A\* trên cùng màn |
| 8 | Tìm lỗi khi chơi thử | Tìm nguyên nhân các lỗi Nguyên phát hiện | Tái hiện lỗi trên GUI thật |
| 9 | Phần còn lại của TV3 | Hoàn thành phần chưa xong, viết bài ôn tập | Chạy toàn bộ test |
| 10 | Git, tài liệu | Chia commit, tạo PR, viết README, kịch bản, nháp báo cáo | Chạy thử các lệnh trong README |

## 1. Đọc đề và tách phần việc (16/10)

**Prompt chính:**
- "scan và chuyển toàn bộ nội dung AI - Project 1.pdf sang file .md"
- "bạn chuyển tiếp file .docx sang .md đi"
- "bạn trích riêng ra một file gồm những phần việc role 5 phải làm (do Nguyên là role 5)"

**Kết quả:** `AI - Project 1.md`, `AI_PP.md` và `TV5_Nguyen_NhiemVu.md`.

**Kiểm chứng:** bản Markdown của kế hoạch được so từ ngữ với file Word gốc.

## 2. Khảo sát repo mẫu (16/10)

**Prompt chính:**
- "bạn clone các repo github trong research về và kiểm tra có sự sai khác nào về GUI hay không"
- "cho Nguyên biết những tiêu chí để đánh giá 1 GUI"

**Kết quả:** báo cáo research mô tả GUI của 2 repo chưa đúng, và không repo nào có GUI đáp ứng đủ mục 3.1 của đề. AI cũng lập bộ tiêu chí đánh giá GUI. Nguyên quyết định chỉ giữ repo TranTai35 để tham khảo.

**Giới hạn:** AI chỉ đọc mã nguồn, chưa chạy thử các repo này.

## 3. Xây dựng GUI (16/10 đến 21/10)

**Prompt chính:**
- "tiến hành thực hiện role 5"
- "theo vai trò Nguyên muốn đổi theme qua onepiece và muốn đổi block thành Buggy có được k"
- "hiện tại đồ án yêu cầu GUI 3D, bạn tiến hành điều chỉnh, nếu có thể xây dựng asset 3D tích hợp vào đồ án luôn"

**Kết quả:** AI viết GUI bằng Tkinter, đổi theme One Piece với khối Buggy, sau đó chuyển sang 3D phối cảnh kèm bộ asset 3D. AI tự viết bộ dựng hình để không thêm thư viện ngoài, giúp đồ án chạy được trên máy sạch.

**Kiểm chứng:** 14 test đạt (6 test cũ và 8 test 3D). AI chạy GUI và chụp màn hình các cảnh lăn khối, tách và ghép, băng vỡ, cầu trồi lên, thắng, xoay camera.

## 4. Ghép với core của nhóm (21/10 đến 26/10)

**Prompt chính:**
- "bạn Nguyên đã cập nhật core cho đồ án, bạn xem và kiểm tra code của Nguyên có cần sửa gì không"
- "các lỗi này có nguyên nhân từ đâu, từ việc code của Nguyên chưa thống nhất với các bạn hay sao, nếu là vậy thì bạn đề xuất hướng sửa là gì"
- "bạn điều chỉnh lại code của Nguyên để phù hợp với core chung của nhóm và thực hiện ghép nối với các phần không lỗi"
- "hiện tại còn phần UCS và A\* là chưa được merge vào code của Nguyên, bạn kiểm tra và xem 2 phương pháp này có thể merge vào chưa"

**Kết quả:** AI xác định nguyên nhân là các phần ngoài chữ ký hàm chưa được nhóm thống nhất, rồi sửa GUI để chạy trên core chung. Khi kiểm tra merge thử, AI phát hiện nhánh A\* lúc đó lỗi import và báo lại, chưa merge nhánh này.

**Kiểm chứng:** 132 test đạt (111 test của nhóm và 21 test GUI). Việc merge thử được làm trên bản sao tạm.

## 5. Thiết kế và chọn màn chơi (26/10 đến 30/10)

**Prompt chính:**
- "hiện tại số màn chơi thực hiện trong source đang là bao nhiêu và đã phù hợp với yêu cầu đề bài chưa"
- "vậy bạn thêm cho Nguyên 3 màn split và 4 màn khó nữa giúp Nguyên"
- "Nguyên cần bao nhiêu màn chơi để thể hiện toàn vẹn các tính năng và các mức độ khác nhau"
- "để chọn ra 10 màn chơi giúp thể hiện toàn bộ đồ án thì bạn nghĩ Nguyên chọn màn nào"
- "nhưng bộ 10 test của bạn đã bao đủ phần experiment chưa, bạn tạo 2 subagent nhằm tự phản biện bản thân"
- "Tiến hành chỉ để lại 10 test cho phần demo của Nguyên"

**Kết quả:** repo tăng từ 26 lên 33 màn. Danh sách màn trong GUI rút còn 10 màn demo, còn file các màn khác vẫn giữ lại.

**Điều chỉnh sau phản biện:** AI tự kết luận bộ 10 màn chưa đủ thay bộ thực nghiệm. Vì vậy bộ 27 màn được giữ cho Experiments, còn bộ 10 màn chỉ dùng để demo.

**Kiểm chứng:** cả 4 solver đều tìm ra lời giải trên từng màn mới, và 165 test đạt tại thời điểm thêm màn.

## 6. Heuristic cho A\* (26/10 đến 30/10)

**Prompt chính:**
- "Nút A\* trên GUI vẫn dùng h = 0 [...] phần này Nguyên có thể tự thay đổi tham số mặc định để chạy với h khác 0 không"
- "thực hiện thay đổi thành có h != 0 cho Nguyên"
- "vậy A\* trong nhóm đã có sự thay đổi trong việc sử dụng h\* chưa"
- "bạn sửa thẳng trong code của Nguyên luôn đi, sau đó tiến hành báo cáo"
- "trong các hàm heuristic này, hàm nào có thể khắc phục việc h = 0 với các màn có split"
- "bạn tạo bản clone để Nguyên test hàm này"
- "tiến hành thay đổi hàm heuristic thành bản hS trong bản chính"

**Kết quả:**
- `relaxed_heuristic`: số lần lăn ít nhất trên bàn nới lỏng, tức mọi cầu luôn mở và bỏ luật fragile. Hàm này vẫn cho h = 0 khi khối đã tách.
- `split_heuristic` (hS): ước lượng cả khi khối đã tách. Ví dụ, số nút mở rộng trên `split/02_split_reunion` giảm từ 4 876 (`relaxed_heuristic`) xuống 339.

**Kiểm chứng và sửa lỗi:**
- hS được thử trên bản clone riêng trước, với 218 test đạt, rồi mới áp vào bản chính.
- Trong lúc kiểm tra, AI phát hiện bản hS đầu tiên tính 0 cho các chỗ ghép không tới được đích, làm ước lượng bị kéo xuống, nên đã sửa lại.

- Sau khi áp hS vào bản chính, toàn bộ test được chạy lại: 210 đạt, 1 bỏ qua, không có lỗi.

## 7. Hàm chi phí của UCS (28/10 đến 30/10)

**Prompt chính:**
- "hiện tại theo Nguyên check thì cost đang luôn bằng path"
- "cho Nguyên biết tất cả các tình huống UCS cập nhật cost (có dẫn chứng code)"
- "tại sao ở chi phí Nguyên không thể set mặc định là 1 mà lại có sự sai khác giữa các chi phí?"
- "bạn đánh giá hàm chi phí của A\* hay UCS là tối ưu hơn"
- "Nguyên đang cần thay đổi sao cho thấy được sự khác biệt giữa A\*, UCS và BFS"
- "tắt việc hiển thị bảng so sánh trên GUI đi (bị rối quá)"

**Kết quả:** Nguyên phát hiện chi phí gần như luôn bằng số bước. AI đo lại trên 30 màn giải được: đường đi của UCS trùng BFS ở cả 30 màn, và chỉ 1 màn có cost khác số bước. Sau đó hàm chi phí được chỉnh để mỗi bước đáp lên băng mỏng tốn thêm 3, nên UCS có thể đi vòng.

Kết quả đo trên `advanced/02_fragile_band` tại thời điểm đó:

| Thuật toán | Số nước | Chi phí | Số nút mở rộng |
|---|---:|---:|---:|
| BFS | 6 | 12 | 50 |
| UCS | 8 | 11 | 48 |
| A\* | 8 | 11 | 23 |

**Quyết định của Nguyên:** AI từng thêm bảng so sánh vào GUI, nhưng Nguyên yêu cầu gỡ vì giao diện bị rối. Số liệu vẫn xem được ở khung Result sau mỗi lần giải.

## 8. Tìm lỗi khi chơi thử (28/10)

**Prompt chính:**
- "hiện tại khi Nguyên test split, có một số màn mà số node mở của UCS lớn hơn BFS, hãy giải thích lí do"
- "Nguyên đang test tại demo 7 khi ấn d -> d thì bị lỗi không vào split được, bạn tiến hành kiểm tra và báo cáo lỗi"
- "không sửa code, thêm vào readme lưu ý này cho Nguyên"

**Kết quả:**
- **UCS mở nhiều nút hơn BFS:** do mô hình chi phí, không phải lỗi. Với chi phí đều, số nút mở của UCS bằng đúng BFS ở cả 8 màn split.
- **Demo 7:** engine vẫn tách đúng khi nhận đủ phím, và một nguyên nhân là bộ gõ tiếng Việt đổi "d d" thành "đ". Theo yêu cầu của Nguyên, code được giữ nguyên, chỉ thêm lưu ý vào README.

**Kiểm chứng:** AI gửi phím vào cửa sổ GUI thật để tái hiện lỗi.

## 9. Hoàn thành phần còn lại của TV3 (28/10)

**Prompt chính:**
- "hiện tại còn các việc của thành viên 3 chưa hoàn thành, việc này không đụng đến logic giải bài, bạn hoàn thành luôn phần việc này của thành viên 3 sau đó tạo ra bài test bao quát toàn bộ nội dung dự án luôn cho Nguyên"

**Kết quả:** AI hoàn thành các phần TV3 còn lại và viết thêm test. AI cũng tạo bài ôn tập 60 câu trắc nghiệm theo 10 chủ đề để chuẩn bị vấn đáp.

**Kiểm chứng:** 188 test đạt, tăng từ 173.

## 10. Git và tài liệu (16/10 đến 28/10)

**Prompt chính:**
- "vậy bây giờ Nguyên có thể chia thành những commit nào để đúng với tiến độ từng giai đoạn"
- "bạn chia ra thành nhiều commit để nhóm Nguyên biết được không"
- "tạo PR lên github cho Nguyên"
- "tiến hành rà soát xem Nguyên cần làm những phần việc nào nữa"
- "vậy bạn cập nhật lại file readme và lên kịch bản quay thử đi"

**Kết quả:**
- Chia thay đổi thành 8 commit theo phần của từng thành viên, tạo PR #7, và tách một bản riêng cho ngày 1 đến 3 lên nhánh `role5-phase1`.
- Viết lại README và viết `TV5_KichBanDemo.md`, lập checklist theo dõi tiến độ.
- Viết `tools/benchmark.py`, đo lại kết quả và soạn nháp `docs/report_astar_experiments_vi.md`, `docs/tv3_report_section_vi.md`.

**Tư vấn của AI:** AI khuyên không sửa ngày commit để giả như làm đúng tiến độ, vì nhóm tính đóng góp dựa trên minh chứng Git.

**Kiểm chứng:** các lệnh chạy 5 solver trong README được chạy thử trên `08_showcase`.

## Nhận xét về việc sử dụng AI

- **Con người phát hiện vấn đề, AI truy nguyên nhân.** Các vấn đề chi phí bằng số bước, UCS mở nhiều nút hơn BFS và lỗi demo 7 đều do Nguyên phát hiện khi chạy thử.
- **Kết quả của AI vẫn cần kiểm tra.** Bản hS đầu tiên có sai sót, và bộ 10 màn đề xuất ban đầu không đủ cho Experiments. Cả hai chỉ lộ ra khi kiểm tra lại hoặc yêu cầu AI tự phản biện.
- **Quyết định cuối do Nguyên đưa ra,** ví dụ gỡ bảng so sánh khỏi GUI, không sửa code ở lỗi demo 7, và thử hS trên bản clone trước khi áp vào bản chính.
