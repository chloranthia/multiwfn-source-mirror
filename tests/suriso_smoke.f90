program suriso_smoke
  use dislin, only: metafl, setfil, disini, nograf, graf3d, suriso, disfin
  implicit none

  integer, parameter :: nx = 3, ny = 4, nz = 5
  real(8) :: x(nx), y(ny), z(nz), field(nx, ny, nz)
  character(512) :: output_file
  integer :: i, j, k

  if (command_argument_count() < 1) stop 1
  call get_command_argument(1, output_file)

  do i = 1, nx
    x(i) = -1.0d0 + 2.0d0 * (i - 1) / (nx - 1)
  end do
  do j = 1, ny
    y(j) = -1.0d0 + 2.0d0 * (j - 1) / (ny - 1)
  end do
  do k = 1, nz
    z(k) = -1.0d0 + 2.0d0 * (k - 1) / (nz - 1)
  end do
  do k = 1, nz
    do j = 1, ny
      do i = 1, nx
        field(i, j, k) = x(i)**2 + y(j)**2 + z(k)**2
      end do
    end do
  end do

  call metafl('PNG')
  call setfil(trim(output_file))
  call disini()
  call nograf()
  call graf3d(-1.0d0, 1.0d0, -1.0d0, 0.5d0, &
              -1.0d0, 1.0d0, -1.0d0, 0.5d0, &
              -1.0d0, 1.0d0, -1.0d0, 0.5d0)
  if (command_argument_count() == 1) then
    call suriso(x, nx, y, ny, z, nz, field, 0.7d0)
  end if
  call disfin()
end program suriso_smoke
