import re

from productos.domain.knowledge import DocumentFormat, ParsedSection


class MarkdownTextParser:
    def parse(self, content: str, document_format: DocumentFormat) -> list[ParsedSection]:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        normalized = re.sub(r"[ \t]+\n", "\n", normalized).strip()
        if document_format == DocumentFormat.TEXT:
            return [ParsedSection(content=normalized)]

        sections: list[ParsedSection] = []
        current_title: str | None = None
        parent_title: str | None = None
        buffer: list[str] = []

        def flush() -> None:
            body = "\n".join(buffer).strip()
            if body:
                sections.append(
                    ParsedSection(
                        title=current_title,
                        parent_title=parent_title,
                        content=body,
                    )
                )
            buffer.clear()

        for line in normalized.splitlines():
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading is None:
                buffer.append(line)
                continue
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1:
                parent_title = title
                current_title = title
            else:
                current_title = title
        flush()
        return sections or [ParsedSection(content=normalized)]
