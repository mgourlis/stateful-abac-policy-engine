interface PaginationProps {
    total: number;
    skip: number;
    limit: number;
    onPageChange: (skip: number) => void;
    onPageSizeChange?: (limit: number) => void;
    pageSizeOptions?: number[];
}

export function Pagination({
    total,
    skip,
    limit,
    onPageChange,
    onPageSizeChange,
    pageSizeOptions = [10, 25, 50, 100],
}: PaginationProps) {
    const currentPage = Math.floor(skip / limit) + 1;
    const totalPages = Math.ceil(total / limit);

    const goToPage = (page: number) => {
        const newSkip = (page - 1) * limit;
        onPageChange(Math.max(0, Math.min(newSkip, (totalPages - 1) * limit)));
    };

    // Generate page numbers to show
    const getPageNumbers = (): (number | '...')[] => {
        if (totalPages <= 7) {
            return Array.from({ length: totalPages }, (_, i) => i + 1);
        }

        const pages: (number | '...')[] = [1];

        if (currentPage > 3) {
            pages.push('...');
        }

        const start = Math.max(2, currentPage - 1);
        const end = Math.min(totalPages - 1, currentPage + 1);

        for (let i = start; i <= end; i++) {
            pages.push(i);
        }

        if (currentPage < totalPages - 2) {
            pages.push('...');
        }

        if (totalPages > 1) {
            pages.push(totalPages);
        }

        return pages;
    };

    if (total === 0) return null;

    return (
        <div className="pagination">
            <div className="pagination-info">
                Showing {skip + 1}–{Math.min(skip + limit, total)} of {total}
            </div>

            <div className="pagination-controls">
                <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => goToPage(currentPage - 1)}
                    disabled={currentPage === 1}
                >
                    ←
                </button>

                {getPageNumbers().map((page, idx) => (
                    page === '...' ? (
                        <span key={`ellipsis-${idx}`} className="pagination-ellipsis">...</span>
                    ) : (
                        <button
                            key={page}
                            className={`btn btn-sm ${currentPage === page ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={() => goToPage(page)}
                        >
                            {page}
                        </button>
                    )
                ))}

                <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => goToPage(currentPage + 1)}
                    disabled={currentPage === totalPages}
                >
                    →
                </button>
            </div>

            {onPageSizeChange && (
                <div className="pagination-size">
                    <select
                        className="form-select"
                        value={limit}
                        onChange={(e) => onPageSizeChange(Number(e.target.value))}
                        style={{ width: 'auto', padding: '0.25rem 0.5rem' }}
                    >
                        {pageSizeOptions.map((size) => (
                            <option key={size} value={size}>
                                {size} / page
                            </option>
                        ))}
                    </select>
                </div>
            )}
        </div>
    );
}
