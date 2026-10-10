# vibe-coding

김현아의 바이브코딩 프로젝트입니다.

- 시작 홈페이지: https://k283199-blip.github.io/vibe-coding/
- URL2QR: https://k283199-blip.github.io/vibe-coding/url2qr/
- QRnShort: https://k283199-blip.github.io/vibe-coding/qrnshort/

## 공개 배포

저장소 Settings → Pages → Build and deployment → Source에서 GitHub Actions를 선택합니다. 웹사이트 파일은 site/에 있습니다.

## 제출 PDF

Actions → ‘Deploy website and build assignment’ → ‘Run workflow’에서 이름(student_name)과 학번(student_id)을 입력하여 실행합니다. 실행이 성공하면 ‘6week-assignment-pdf’ 결과물을 내려받습니다. PDF는 A4 3쪽이며 실제 배포 사이트에서 촬영한 화면과 클릭 가능한 URL을 포함합니다. PDF 생성 전에 QR·단축주소·URL2QR 연결을 확인합니다. 단축 서비스에 문제가 있으면 성공으로 표시하거나 결과를 꾸미지 않고 실행을 실패시킵니다.

학번은 저장소 코드에 기록하지 않습니다. 입력한 이름·학번은 실행 로그에서 가려지며 제출 PDF에만 표시됩니다. PDF와 검증 이미지는 Actions 결과물에만 보관되며 웹사이트에는 포함하지 않습니다.

## 기능

홈페이지 검색과 빠른 링크, 브라우저 메모 저장. URL2QR의 QR 생성·PNG 저장. QRnShort의 QR 생성·is.gd 단축주소 생성·복사·새 창 열기. is.gd 단축주소는 실제 공개 서비스 결과를 사용하며 변환 버튼을 누를 때만 요청합니다.

## 외부 라이브러리

QR 생성: [QRCode.js](https://github.com/davidshimjs/qrcodejs), MIT License. 원본 라이브러리와 라이선스를 site/assets/에 포함했습니다.
