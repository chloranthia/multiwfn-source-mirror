program blas_lapack_regression
    use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
    implicit none
    integer :: info, i, method, lwork, iwork(16)
    double precision :: a(2,2), original(2,2), b(2,2), c(2,2)
    double precision :: w(2), wi(2), u(2,2), vt(2,2), unused(1,1), work(16)
    double precision, allocatable :: svd_work(:)

    ! Default INTEGER and DOUBLE PRECISION match the upstream F77 calls.
    original = reshape([2d0, 1d0, 1d0, 2d0], [2,2])
    a = original
    b = reshape([1d0, 2d0, 3d0, 4d0], [2,2])
    c = 1d0
    call dgemm('N', 'N', 2, 2, 2, 2d0, a, 2, b, 2, 3d0, c, 2)
    call check_close(reshape(c, [4]), [11d0, 13d0, 23d0, 25d0], 'DGEMM')

    a = original
    call dsyev('V', 'U', 2, a, 2, w, work, 5, info)
    call check_info(info, 'DSYEV')
    call check_close(w, [1d0, 3d0], 'DSYEV eigenvalues')
    do i = 1, 2
        call check_close(matmul(original, a(:,i)), w(i)*a(:,i), 'DSYEV eigenvectors')
    end do
    call check_orthogonal(a, 'DSYEV orthogonality')

    original = reshape([1d0, 0d0, 2d0, 3d0], [2,2])
    a = original
    call dgeev('N', 'V', 2, a, 2, w, wi, unused, 1, u, 2, work, 16, info)
    call check_info(info, 'DGEEV')
    call check_close([minval(w), maxval(w)], [1d0, 3d0], 'DGEEV eigenvalues')
    call check_close(wi, [0d0, 0d0], 'DGEEV imaginary parts')
    do i = 1, 2
        call check_close(matmul(original, u(:,i)), w(i)*u(:,i), 'DGEEV eigenvectors')
        call check_close([sum(u(:,i)**2)], [1d0], 'DGEEV normalization')
    end do

    ! Query and allocate workspace just as Multiwfn's SVD wrapper does.
    original = reshape([2d0, 1d0, 1d0, 2d0], [2,2])
    do method = 1, 2
        a = original
        if (method == 1) then
            call dgesvd('A', 'A', 2, 2, a, 2, w, u, 2, vt, 2, work, -1, info)
            call check_info(info, 'DGESVD workspace query')
        else
            call dgesdd('A', 2, 2, a, 2, w, u, 2, vt, 2, work, -1, iwork, info)
            call check_info(info, 'DGESDD workspace query')
        end if
        if (.not. ieee_is_finite(work(1)) .or. work(1) < 1d0) error stop 'Invalid SVD workspace'
        lwork = nint(work(1))
        allocate(svd_work(lwork))
        a = original
        if (method == 1) then
            call dgesvd('A', 'A', 2, 2, a, 2, w, u, 2, vt, 2, svd_work, lwork, info)
            call check_info(info, 'DGESVD')
        else
            call dgesdd('A', 2, 2, a, 2, w, u, 2, vt, 2, svd_work, lwork, iwork, info)
            call check_info(info, 'DGESDD')
        end if
        call check_close(w, [3d0, 1d0], 'SVD singular values')
        call check_orthogonal(u, 'SVD left vectors')
        call check_orthogonal(transpose(vt), 'SVD right vectors')
        b = u
        do i = 1, 2
            b(:,i) = b(:,i)*w(i)
        end do
        call check_close(reshape(matmul(b, vt), [4]), reshape(original, [4]), 'SVD reconstruction')
        deallocate(svd_work)
    end do

    print *, 'BLAS/LAPACK numerical regression passed'
contains
    subroutine check_info(status, label)
        integer, intent(in) :: status
        character(*), intent(in) :: label
        if (status /= 0) then
            print *, label, ': INFO = ', status
            error stop 1
        end if
    end subroutine

    subroutine check_close(actual, expected, label)
        double precision, intent(in) :: actual(:), expected(:)
        character(*), intent(in) :: label
        if (.not. all(ieee_is_finite(actual)) .or. &
            any(abs(actual - expected) > 1d-10*max(1d0, abs(expected)))) then
            print *, label, ': got ', actual, ', expected ', expected
            error stop 1
        end if
    end subroutine

    subroutine check_orthogonal(vectors, label)
        double precision, intent(in) :: vectors(2,2)
        character(*), intent(in) :: label
        call check_close(reshape(matmul(transpose(vectors), vectors), [4]), &
            [1d0, 0d0, 0d0, 1d0], label)
    end subroutine
end program
