! **********************************CCD Image preprocessing*************************************
!program name:01pre.f90
!
! function:1）产生文件列表(fits.lst,bias.lst,dark.lst,flat.lst)，保存入相应文件夹。
!          2) 预处理模式1：不做任何处理(在"adias.cfg"文件中bias=0;dark=0;flat=0;super_flat=0)
!             预处理模式2：使用bias/dark/flat修正(在"adias.cfg"文件中bias=1;dark=1;flat=1)
!             预处理模式3：使用flat修正(在"adias.cfg"文件中bias=0;dark=0;flat=1;super_flat=0)
!             预处理模式4：使用超极背景(在"adias.cfg"文件中bias=0;dark=0;flat=0;super_flat=1)
!          3）输出修改平场后的图像: *n_fit
!    input:0）注意fits图像保存路径：请分别将图像分别存入相应名称文件夹（...fits；...bias；...dark；...flat）
!          1) 配置文件1（图像存储路径文件fitspath.in（按日存储））：例F:\000obs\SHAO\200609\20060918\fits
!          2) 配置文件信息（adias.cfg）
!               2.1）1biasflag=0 %使用bias修正的开关
!               2.2）1darkflag=0 %使用dark修正的开关
!               2.3）1superflag=1 %使用超级背景修正的开关
!               2.4）1med_length=1  %使用中值滤波算法的窗口长度
!               2.5）1med_width=25  %使用中值滤波算法的窗口宽度
!               2.6）1bkgdmode=2    %对超级背景扣除的模式（1-使用除法；2-使用减法）
!               2.6）enhance_flag=1 %使用图像增强的开关
!   output:1）图像文件列表（相应图像文件夹内），fits.lst/bias.lst/dark.lst/flat.lst
!          2) 预处理后图像文件: *_n.fit
!          2）合并后图像文件：bias/dark/flat file: *_n.fit在相应文件夹（如果有）
!  子程序：1）fits_data(fitsfile,fitsdata,exptime,npx)
!                      获取fits图像数据（已增加对非整块像素的读取）
!          2) fits_com(filepath,nfitsfile)
!                      合并图像文件
!          3) fits_subtract(fitsfile,basefile,nfitsfile)
!                      扣除fits叠加噪声
!          4) fits_prepro(fitsfile,biasfile,darkfile,flatfile,nfitsfile)
!                      使用bias/dark/flat预处理图像（bias/dark无时，可作为处理乘性噪声用）
!          5) fits_superbkgd_pro(fitsfile,med_length,med_width,enhance_flag,nfitsfile)
!                      对原始图像进行中值滤波生成超极平场，并对原始图像进行预处理
!          6) fits_enhance(mdat,naxis1,naxis2,mdat_en)
!                      图像增强（九宫格中心像素取9像素均值）
!          7) cal_b(mdat,npx,bkgd,bkgdsigma)
!                      计算fits图像背景值及其sigma（已扣除星象影响）
!          8) shell_sort(A,N)
!                      对数列进行排序（排序慢，待优化）
!          9) seq2mat(seqnum,naxis1,naxis2,nli,nar)
!                      一维数组变为二维数组
!         10) mat2seq(nli,nar,naxis1,naxis2,seq)
!                      二维数组变为一维数组

! V1.0 by zhy 2020.12.10
! V2.0 by zhy 2024.9.30  程序中间输出中文化

      program pre
       implicit none
       integer i,m,s,ic,ic1,superflag,biasflag,darkflag,flatflag,bkgdmode
       integer med_length,med_width,n,enhance_flag
       parameter(m=1000)
       parameter(s=9500000)
       character*300 fitspath,biaspath,darkpath,flatpath,finfor,cfgfile
       character*200 tempcha,cpfits,cpbias,cpdark,cpflat
       character*300 fitsout,biasout,darkout,flatout
       character*200 fitsfile,biasfile,darkfile,flatfile
       character*200 nfitsfile,nbiasfile,ndarkfile,nflatfile,bnfitsfile,dnfitsfile
       real*8 objra,rah,ram,ras,objde,ded,dem,des,objmag
       character*1 deflag
       integer*4 year,month,day,hh,mm,npx,bitpix,naxis1,naxis2 !!2^32-1 @2147483647(10位)
       real*8 bscale,bzero,gain,ss
	   real*8 exptime,bexptime,dexptime,fexptime,flexptime
       real*8 sumbias,sumdark,sumflat,nbias,ndark,nflat
       real*8 biasdata(s),darkdata(s),flatdata(s),fitsdata(s)
       integer*4 flag(4),flag1(4),flag2(4),n_day

!01--读fits文件路径（fitspath.in），按照文件内容逐日处理
       open(1,file='fitspath.in',status='old')
!       open(1,file='D:\00adias\exe\200809fitspath.in',status='old')
       n_day=0
77     read(1,'(a)',end=777) fitspath
       fitspath=trim(fitspath)
       n_day=n_day+1  !用以记录共处理几天数据
    write(*,'(i3,a,a,a)')  n_day,'-','本日fits文件：',trim(fitspath)

!02--读配置文件（adias2024.cfg）
!    open(11,file='D:\00adias\exe\200809adias.cfg')
     open(11,file='adias2024.cfg')
      do i=1,m
        read(11,'(a)',end=100) tempcha

        ic=index(tempcha,'1biasflag=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+1),*) biasflag
        endif

        ic=index(tempcha,'1darkflag=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+1),*) darkflag
        endif

        ic=index(tempcha,'1flatflag=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+1),*) flatflag
        endif

        ic=index(tempcha,'1superflag=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+1),*) superflag
        endif

        ic=index(tempcha,'1med_length=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+3),*) med_length
        endif

        ic=index(tempcha,'1med_width=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+3),*) med_width
        endif
! 读取中值滤波后得到的背景图像的扣除方法，1除法，2减法
        ic=index(tempcha,'1bkgdmode=')
        if(ic.gt.0) then
          ic1=index(tempcha,'=')
          read(tempcha(ic1+1:ic1+3),*) bkgdmode
        endif

	      ic=index(tempcha,'1enhance_flag=')
	      if(ic.gt.0) then
	        ic1=index(tempcha,'=')
	        read(tempcha(ic1+1:ic1+2),*) enhance_flag
        endif

      enddo
100   close(11)
!需要对所有批次数据统一滤波窗口时使用
!    med_length=15
!     med_width=1
!      bkgdmode=2
!      enhance_flag=0
!      med_length=15
!      med_width=1
!03--删除本路径下历史处理遗留数据，并生成相应文件列表到lst文件（含fits;bias;dark;flat）
!      (CCDVIEW can only open *.fit file. so rename *fits to *fit)
	  fitsout=trim(fitspath)//'/'//'fits.lst'
    !---- generate shell script instead of bat ----
open(12,file='getfile.sh',status='replace')
write(12,'(a)') '#!/bin/bash'
write(12,'(a)') 'cd "'//trim(fitspath)//'"'
write(12,'(a)') 'rm -f *.lst *_n.fit *_n.fit.flat.fit'
write(12,'(a)') 'for f in *.fit; do echo "$PWD/$f"; done > fits.lst'
if(biasflag>0) then
   biaspath=fitspath(1:len(trim(fitspath))-4)//'bias'
   write(12,'(a)') 'cd "'//trim(biaspath)//'"'
   write(12,'(a)') 'rm -f *.lst *_n.fit *.out'
   write(12,'(a)') 'for f in *.fit; do echo "$PWD/$f"; done > bias.lst'
endif
if(darkflag>0) then
   darkpath=fitspath(1:len(trim(fitspath))-4)//'dark'
   write(12,'(a)') 'cd "'//trim(darkpath)//'"'
   write(12,'(a)') 'rm -f *.lst *_n.fit *.out'
   write(12,'(a)') 'for f in *.fit; do echo "$PWD/$f"; done > dark.lst'
endif
if(flatflag>0) then
   flatpath=fitspath(1:len(trim(fitspath))-4)//'flat'
   write(12,'(a)') 'cd "'//trim(flatpath)//'"'
   write(12,'(a)') 'rm -f *_n.fit'
   write(12,'(a)') 'for f in *.fit; do echo "$PWD/$f"; done > flat.lst'
endif
close(12)
call system('chmod +x getfile.sh')
call system('./getfile.sh')
!----------------------------------------------
      write(*,*)
      write(*,'(a,a)') '已生成fit文件序列-->',trim(fitsout)
      write(*,*)

      if((biasflag+darkflag+flatflag+superflag).lt.0.5) goto 999
!04--显示文件列表，并统计待处理图像数目,显示配置文件中预处理模式设置
     !注意优先选择超极平场，所以如果不用，一定设0
      open(14,file=fitsout)
      do i=1,m
        read(14,'(a)',end=101) fitsfile
        write(*,'(i3.3,a,a)') i,'-',trim(fitsfile)
      end do
101   close(14)
      write(*,'(a,i5)') '待处理fit文件数目：',i-1
      !显示配置文件中预处理模式设置
      !注意优先选择超极平场，所以如果不用，一定设0
      write(*,*)
	  write(*,'(a)')    '预处理模式（传统/中值滤波）：bias/dark/flat/superbkgd/enhance'
      write(*,'(a,5i3)')  '        ',biasflag,darkflag,flatflag,superflag,enhance_flag
!05--按照与处理设置模式进行预处理（bias/dark/flat模式；superbkgd模式）
!051---bias/dark/flat模式:
!051------对bias/dark/flat图像进行合并（如有）
	  nbiasfile=trim(biaspath)//'/'//'bias_n.fit'
	  ndarkfile=trim(darkpath)//'/'//'dark_n.fit'
	  nflatfile=trim(flatpath)//'/'//'flat_n.fit'
	  if(biasflag>0)then
		  call fits_com(biasout,nbiasfile)
		  write(*,'(a,a)')'combine bias-files to:',trim(nbiasfile)
	  endif
	  if(darkflag>0)then
		  call fits_com(darkout,ndarkfile)
		  write(*,'(a,a)')'combine dark-files to:',trim(ndarkfile)
	  endif
	  if(flatflag>0)then
		  call fits_com(flatout,nflatfile)
		  write(*,'(a,a)')'combine flat-files to:',trim(nflatfile)
	  endif
!051-----使用bias/dark/flat预处理图像
      if (superflag.eq.0)then
        if (biasflag==1.and.darkflag==1.and.flatflag==1) then
           write(*,'(a)')'===========使用bias/dark/flat进行图像预处理==========='
           write(*,*)
           open(15,file=fitsout)
           do i=1,m
             read(15,'(a)',end=105) fitsfile
             fitsfile=trim(fitsfile)
             ic=index(fitsfile,'.fit')
	         nfitsfile=fitsfile(1:ic-1)//'_n.fit'
             write(*,'(i3.3,a,a)')i,'-',trim(fitsfile)
             call fits_prepro(fitsfile,nbiasfile,ndarkfile,nflatfile,enhance_flag,nfitsfile)!可选择是否增强（均值滤波）
             write(*,'(a,a)')     '经过传统模式预处理后的新图像路径: ',trim(nfitsfile)
            enddo
          endif
105       close(15)
!052--仅使用flat预处理模式：删除此模式选择
!-------仅flat，bias和dark文件认为全0（叠加噪声）（子程序同前fits_prepro）
       if (biasflag==0.and.darkflag==0.and.flatflag==1) then
         write(*,'(a)')'===========使用flat进行图像预处理==========='
         write(*,*)
         nbiasfile='none'
         ndarkfile='none'
         open(15,file=fitsout)
         do i=1,m
            read(15,'(a)',end=106) fitsfile
            fitsfile=trim(fitsfile)
            ic=index(fitsfile,'.fit')
            nfitsfile=fitsfile(1:ic-1)//'_n.fit'
             write(*,'(i3.3,a,a)')i,'-',trim(fitsfile)
             call fits_prepro(fitsfile,nbiasfile,ndarkfile,nflatfile,enhance_flag,nfitsfile)
             write(*,'(a,a)')     '经过仅flat处理模式预处理后的新图像路径:  ',trim(nfitsfile)
         enddo
       endif
106    close(15)

!05--superflag=1,使用中值滤波将星象视作椒盐噪声进行去除，平滑后生成背景图，注意窗口的选择（滤掉星象但保留主星及部分光晕，用以相减时扣除光晕）
!052--使用superbkgd预处理模式：
!-------使用中值滤波获得背景图像（若需显示平场图像，fits_superbkgd_pro内可取消注释）
     else
        write(*,'(a)')'===========使用超极平场进行图像预处理==========='
        write(*,*)
        open(15,file=fitsout)
        do i=1,m
          read(15,'(a)',end=107) fitsfile
          fitsfile=trim(fitsfile)
          ic=index(fitsfile,'.fit')
          nfitsfile=fitsfile(1:ic-1)//'_n.fit'
          write(*,'(i3.3,a,a)')i,'-',trim(fitsfile)
          call fits_superbkgd_pro(fitsfile,med_length,med_width,bkgdmode,enhance_flag,nfitsfile)
          write(*,'(a,a)')     '                 经中值滤波模式预处理后的新图像路径:  ',trim(nfitsfile)
        enddo
    endif
107 close(15)
    write(*,'(a)')    '================01 Pre-Program execution summary=================='
    write(*,'(a,i4)') '    完成图像预处理（*_n.fit），共预处理图像：',i-1
    write(*,'(a)')    '    完成预处理后的新的fits图像的名字命名为： *_n.fit.'
    write(*,'(a)')    '================================================================='
!处理下一天数据
    goto 77  !回到程序第一行读取inputfile.in文件
777 close(1)
    write(*,'(a,i5)') '预处理结束，共处理数据天数：',n_day
    goto 9991
999  write(*,'(a)') '据配置文件，不对图像进行任何预处理！！！！'
9991    write(*,'(a)')    '================================================================='
    end program pre
!*********************************************************************************

!=========================subtoutine==========================
      subroutine fits_data(fitsfile,fitsdata,exptime,npx)
!         function:get the fitsdata to fitsdata(npx)
!            input:fitsfile(fits file name)
!           output: fitsdata(一维数组：naxis1*naxis2,已*bscale+bzero)
!                   exptime （本幅图像的曝光时间）
       implicit real*8(a-h,o-z)
       parameter(maxheadrec=10)
       character*200 fitsfile
       integer *4 nmaxre,nbyf,npxf,i
       parameter (nmaxre=15000,nbyf=2880,npxf=1440)
       integer *1 recdat(nbyf),recsw(nbyf)
       integer *2 recpx(npxf)
       equivalence (recsw,recpx)
       integer *4 npx,ntotpx,nrec,s
       integer *4 naxis1,naxis2,seqnum,nli,nar,bitpix
       character*2880 rhead
       real*8 bzero,bscale,gain,exptime
       parameter(s=9500000)
       real*8 fitsdata(s)
!  读取图像头文件相关信息
       open(33,file=fitsfile,status='old',access='direct',recl=nbyf)
       do i=1,maxheadrec
         read(33,rec=i) rhead

         ic=index(rhead,'BITPIX  =')
         if(ic.ne.0) then
           read(rhead(ic+9:ic+29),'(i21)') bitpix
         endif

         ic=index(rhead,'NAXIS1  =')
         if(ic.ne.0) then
           read(rhead(ic+9:ic+29),'(i21)') naxis1
         endif

         ic=index(rhead,'NAXIS2  =')
         if(ic.ne.0) then
           read(rhead(ic+9:ic+29),'(i21)') naxis2
         endif

         ic=index(rhead,'BSCALE  =')
         if(ic.ne.0) then
           read(rhead(ic+9:ic+29),*) bscale
         endif

         ic=index(rhead,'BZERO   =')
         if(ic.ne.0) then
           read(rhead(ic+9:ic+29),*) bzero
         endif

         ic=index(rhead,'EXPTIME =')
         if(ic.ne.0) then
           read(rhead(ic+9:ic+29),*) exptime
         endif

         ic=index(rhead,'END            ')
         if(ic.ne.0) then
           goto 93
         endif
       enddo
93    nrec=i+1
      npx =1
      ntotpx = naxis1*naxis2
!  计算共有多少个数据块nbyf=2880,npxf=1440
      numdatarec=int(ntotpx*bitpix/8/nbyf)
      do i=1,numdatarec
        read(33,rec=nrec) recdat
        do k = 2,2880,2
          recsw(k-1)=recdat(k)
          recsw(k)=recdat(k-1)
        enddo

        do j = 1,npxf
          fitsdata(npx) = recpx(j)*bscale+bzero
          if(fitsdata(npx).lt.0) fitsdata(npx)=fitsdata(npx)+65536.0d0 !!!
          npx = npx + 1
        enddo
		nrec=nrec+1
      enddo
!   读取剩余像素（2019.10.11增）
      read(33,rec=nrec) recdat
      do k = 2,2*(ntotpx-1440*(numdatarec)),2
          recsw(k-1)=recdat(k)
          recsw(k)=recdat(k-1)
      enddo

      do j = 1,ntotpx-1440*(numdatarec)
          fitsdata(npx) = recpx(j)*BScale+bzero
          if(fitsdata(npx).lt.0) fitsdata(npx)=fitsdata(npx)+65536.0D0
          npx = npx + 1
      enddo
      npx=npx-1
	  close(33)
!一维数组变为二维矩阵（可实现输出二维矩阵，目前未用）
!      fitsdata=0.0d0
!      do i=1,npx
!        call seq2mat(i,naxis1,naxis2,nli,nar)
!        fitsdata(nli,nar)=mdat(i)
!      enddo
      end subroutine fits_data


	  subroutine fits_com(filepath,nfitsfile)
!       function:combine several fits images(average)
!          input:filepath-fits file path（.lst文件）
!         output: nfitsfile(new fits file name)
!		   note1:nfitsdata---has been averaged to per second.
!					 so, according the nth fitsfile exptime
!		     *fitsdata*exptime===nfitsfile data
!		   note2:bias file exptime=0,so if exptime=0,then set it=1.0
!
      implicit real*8(a-h,o-z)
      parameter(maxheadrec=10,m=100)
      character*200 filepath,fitsfile,nfitsfile
      integer *4 nmaxre,nbyf,npxf,i,fn
      parameter (nmaxre=15000,nbyf=2880,npxf=1440)
      integer *1 recdat(nbyf),recsw(nbyf)
      integer *2 recpx(npxf)
      equivalence (recsw,recpx)
      integer *4 naxis1,naxis2,npx,ntotpx,nrec,nrec2,bitpix,s
      character *2880 rhead
      real*8 bzero,bscale,gain,fexptime,bexptime
      parameter(s=9500000)
      real*8 fitsdata(s),nfitsdata(s),sumdata(s)

      open(4,file=filepath,status='old')
	  open(22,file=nfitsfile,status='replace',access='direct',recl=nbyf)
	  sumdata=0
      fn=0
      do n=1,m
        read(4,'(a)',end=100) fitsfile
		fitsfile=trim(fitsfile)
        fn=fn+1
		!if (fn==n)then
		  open(3,file=fitsfile,status='old',access='direct',recl=nbyf)
		  do i=1,maxheadrec
			read(3,rec=i) rhead
			write(22,rec=i) rhead

			ic=index(rhead,'BITPIX  =')
			if(ic.ne.0) then
			  read(rhead(ic+9:ic+29),'(i21)') bitpix
			endif

			ic=index(rhead,'NAXIS1  =')
			if(ic.ne.0) then
			  read(rhead(ic+9:ic+29),'(i21)') naxis1
			endif

			ic=index(rhead,'NAXIS2  =')
			if(ic.ne.0) then
			  read(rhead(ic+9:ic+29),'(i21)') naxis2
			endif

			ic=index(rhead,'BSCALE  =')
			if(ic.ne.0) then
			  read(rhead(ic+9:ic+29),*) bscale
			endif

			ic=index(rhead,'BZERO   =')
			if(ic.ne.0) then
			  read(rhead(ic+9:ic+29),*) bzero
			endif

			ic=index(rhead,'EXPTIME =')
			if(ic.ne.0) then
			  read(rhead(ic+9:ic+29),*) nexptime
			endif

			ic=index(rhead,'END            ')
			if(ic.ne.0) then
			  goto 93
			endif
		  enddo
93        close(3)
		  nrec=i+1
		  nrec2=nrec
		!endif
		call fits_data(fitsfile,fitsdata,exptime,npx)

		if(exptime==0)then
			exptime=1.0   !bias,关快门0秒曝光，
		endif
		sumdata=sumdata+fitsdata/exptime
	   end do
100	   close(4)
	   if(nexptime==0)then
			nexptime=1.0
       endif
!合并后图像数据为平均值
		nfitsdata=sumdata/fn*nexptime !合并后图像头文件与最后一幅图像曝光时间同,bias,曝光时间为0时，新文件中exptime依然为0
!写合并后的fits文件
		ntotpx=naxis1*naxis2
        numdatarec=int(ntotpx*bitpix/8/nbyf)
		npx=1
		do i=1,numdatarec
			do j = 1,npxf
			  recpx(j)=(nfitsdata(npx)-bzero)/bscale
			  npx = npx + 1
			enddo

			do k = 2,2880,2
			  recdat(k)=recsw(k-1)
			  recdat(k-1)=recsw(k)
			enddo
			write(22,rec=nrec2) recdat
			nrec2=nrec2+1
        enddo
!补充剩余像素2019-10-11
!      write(*,*) ntotpx-1440*(numdatarec)
        do j=1,ntotpx-1440*(numdatarec)  !256
          recpx(j)=(bkgd-bzero)/bscale
        enddo

	    do k = 2,2*(ntotpx-1440*(numdatarec)),2
		  recdat(k)=recsw(k-1)
		  recdat(k-1)=recsw(k)
     	enddo
	    write(22,rec=nrec2) recdat
		 close(22)

		end subroutine fits_com

      subroutine fits_subtract(fitsfile,basefile,nfitsfile)
!       function:Subtract the two images（bias, dark）
!          input:fitsfile(fits file name)
!                basefile(base file name)
!         output: nfitsfile(fitsfile-basefile)
!       注意：本程序在pre中目前未用，fits_prepro程序进行了判断重写
!             本程序可用。
      implicit real*8(a-h,o-z)
      parameter(maxheadrec=10)
      character*200 fitsfile,basefile,nfitsfile
      integer *4 nmaxre,nbyf,npxf,i
      parameter (nmaxre=15000,nbyf=2880,npxf=1440)
      integer *1 recdat(nbyf),recsw(nbyf)
      integer *2 recpx(npxf)
      equivalence (recsw,recpx)
      integer *4 naxis1,naxis2,npx,ntotpx,nrec,nrec2,bitpix,s
      character *2880 rhead
      real*8 bzero,bscale,gain,fexptime,bexptime
      parameter(s=9500000)
      real*8 fitsdata(s),basedata(s),nfitsdata(s)

!新图像的头文件与原始图像同
      open(2,file=fitsfile,status='old',access='direct',recl=nbyf)
      open(22,file=nfitsfile,status='replace',access='direct',recl=nbyf)

      do i=1,maxheadrec
        read(2,rec=i) rhead
        write(22,rec=i) rhead

        ic=index(rhead,'BITPIX  =')
        if(ic.ne.0) then
          read(rhead(ic+9:ic+29),'(i21)') bitpix
        endif

        ic=index(rhead,'NAXIS1  =')
        if(ic.ne.0) then
          read(rhead(ic+9:ic+29),'(i21)') naxis1
        endif

        ic=index(rhead,'NAXIS2  =')
        if(ic.ne.0) then
          read(rhead(ic+9:ic+29),'(i21)') naxis2
        endif

        ic=index(rhead,'BSCALE  =')
        if(ic.ne.0) then
          read(rhead(ic+9:ic+29),*) bscale
        endif

        ic=index(rhead,'BZERO   =')
        if(ic.ne.0) then
          read(rhead(ic+9:ic+29),*) bzero
        endif

        ic=index(rhead,'EXPTIME =')
        if(ic.ne.0) then
          read(rhead(ic+9:ic+29),*) exptime
        endif

        ic=index(rhead,'END            ')
        if(ic.ne.0) then
          goto 93
        endif
      enddo
93    close(2)
      nrec=i+1
      nrec2=nrec

      call fits_data(fitsfile,fitsdata,fexptime,npx)
      call fits_data(basefile,basedata,bexptime,npx)
!exptime=0-->bias;exptime!=0-->dark
      if (bexptime>0) then
        nfitsdata=fitsdata-(basedata/bexptime*fexptime)!dark
      else
        nfitsdata=fitsdata-basedata !bias，图像合并后的basedata图像中头文件与原文件同
	  endif
!写扣除叠加噪声后的新图像文件
	  ntotpx=naxis1*naxis2
      numdatarec=int(ntotpx*bitpix/8/nbyf)
      npx=1
      do i=1,numdatarec
        do j = 1,npxf
          recpx(j)=(nfitsdata(npx)-bzero)/bscale
          npx = npx + 1
        enddo

        do k = 2,2880,2
          recdat(k)=recsw(k-1)
          recdat(k-1)=recsw(k)
        enddo
        write(22,rec=nrec2) recdat
        nrec2=nrec2+1
      enddo
!补充剩余像素2019-10-11
!      write(*,*) ntotpx-1440*(numdatarec)
        do j=1,ntotpx-1440*(numdatarec)  !256
          recpx(j)=(bkgd-bzero)/bscale
        enddo

	    do k = 2,2*(ntotpx-1440*(numdatarec)),2
		  recdat(k)=recsw(k-1)
		  recdat(k-1)=recsw(k)
     	enddo
	    write(22,rec=nrec2) recdat
      close(22)
    end subroutine fits_subtract



      subroutine fits_prepro(fitsfile,biasfile,darkfile,flatfile,enhance_flag,nfitsfile)
!       function:process the multiplicative noise（flat）
!          input:fitsfile(fits file name)
!                biasfile(bias file name)
!                darkfile(dark file name)(/dexptime*fexptime)
!                flatfile(flat file name)
!         output:nfitsfile(new fits file name)
!注意：本程序可对于bias/dark文件进行判断，若无，则默认为直接做flat处理
        implicit real*8(a-h,o-z)
		parameter(maxheadrec=10)
        character*200 fitsfile,biasfile,darkfile,flatfile,nfitsfile
        integer *4 nmaxre,nbyf,npxf,i,enhance_flag
        parameter (nmaxre=15000,nbyf=2880,npxf=1440)
        integer *1 recdat(nbyf),recsw(nbyf)
        integer *2 recpx(npxf)
        equivalence (recsw,recpx)
        integer *4 naxis1,naxis2,npx,ntotpx,nrec,nrec2,bitpix,s
        character *2880 rhead
        real*8 bzero,bscale,gain,fexptime,bexptime,dexptime,flexptime
        parameter(s=9500000)
        real*8 fitsdata(s),biasdata(s),darkdata(s)
        real*8 flatdata(s),nfitsdata(s),flatmean,mdat_en(s)
        real*8 bkgd,bkgdsigma,b_bkgd,b_bkgdsigma,d_bkgd,d_bkgdsigma,fl_bkgd,fl_bkgdsigma
        open(2,file=fitsfile,status='old',access='direct',recl=nbyf)
        open(22,file=nfitsfile,status='replace',access='direct',recl=nbyf)
!新图像头文件与原始头文件同
        do i=1,maxheadrec
          read(2,rec=i) rhead
          write(22,rec=i) rhead

          ic=index(rhead,'BITPIX  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),'(i21)') bitpix
          endif

          ic=index(rhead,'NAXIS1  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),'(i21)') naxis1
          endif

          ic=index(rhead,'NAXIS2  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),'(i21)') naxis2
          endif

          ic=index(rhead,'BSCALE  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),*) bscale
          endif

          ic=index(rhead,'BZERO   =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),*) bzero
          endif

          ic=index(rhead,'EXPTIME =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),*) exptime
          endif

          ic=index(rhead,'END            ')
          if(ic.ne.0) then
            goto 93
          endif
        enddo
  93    close(2)
        nrec=i+1
        nrec2=nrec


        call fits_data(fitsfile,fitsdata,fexptime,npx)
        call cal_b(fitsdata,npx,bkgd,bkgdsigma)
        write(*,'(a,2f10.3)')     '  Before pre-fits(image-bkgd,sigma)：',bkgd,bkgdsigma

		if(biasfile=='none')then
			biasdata=0.0
			bexptime=1.0
		else
			call fits_data(biasfile,biasdata,bexptime,npx)
        endif
        call cal_b(biasdata,npx,b_bkgd,b_bkgdsigma)
        write(*,'(a,2f10.3)') '  合并后的Bias(image-bkgd,sigma)：',b_bkgd,b_bkgdsigma
		if(darkfile=='none')then
			darkdata=0.0
			dexptime=1.0
		else
			call fits_data(darkfile,darkdata,dexptime,npx)
        endif
        call cal_b(darkdata,npx,d_bkgd,d_bkgdsigma)
        write(*,'(a,2f10.3)') '  合并后平均每秒的Dark(image-bkgd,sigma)：',d_bkgd,d_bkgdsigma

        call fits_data(flatfile,flatdata,flexptime,npx)
        call cal_b(flatdata,npx,fl_bkgd,fl_bkgdsigma)
        write(*,'(a,2f10.3)') '  合并后平均每秒的Flat(image-bkgd,sigma)：',fl_bkgd,fl_bkgdsigma
        !pause
! 1.56拍摄平场有坏边，1026-1056近30像素，灰度值仅1980左右，而其余像素至少14700，平场sig=270
!故认为假设像素<bkgd-20sig,则将其认为设置为bkgd值
        do i=1,npx
          if(flatdata(i).le.(bkgd-20*bkgdsigma)) flatdata(i)=fl_bkgd
        enddo
        darkdata=darkdata/dexptime-biasdata
        fitsdata=fitsdata-biasdata-darkdata*fexptime
        flatdata=flatdata-biasdata-darkdata*flexptime
		flatdata=flatdata/flexptime*fexptime

        meanflat=sum(flatdata)/npx
        do i=1,npx
            if(flatdata(i)==0.0) flatdata(i)=1.0
            nfitsdata(i)=fitsdata(i)/flatdata(i)*meanflat
        enddo
        call cal_b(nfitsdata,npx,bkgd,bkgdsigma)
        write(*,'(a,2f10.3)')     '        After pre(image-bkgd,sigma)：',bkgd,bkgdsigma

        mdat_en=nfitsdata
        if(enhance_flag.eq.1)then
           call fits_enhance(nfitsdata,naxis1,naxis2,mdat_en)
           call cal_b(mdat_en,npx,bkgd,bkgdsigma)
           write(*,'(a,2f10.3)')  '    After enhance(image-bkgd,sigma)：',bkgd,bkgdsigma
        endif
!写预处理后的新文件
		ntotpx=naxis1*naxis2
        numdatarec=int(ntotpx*bitpix/8/nbyf)
        npx=1
        do i=1,numdatarec
          do j = 1,npxf
            recpx(j)=(nfitsdata(npx)-bzero)/bscale
            npx = npx + 1
          enddo
          do k = 2,2880,2
            recdat(k)=recsw(k-1)
            recdat(k-1)=recsw(k)
          enddo
          write(22,rec=nrec2) recdat
          nrec2=nrec2+1
        enddo
!补充剩余像素2019-10-11
        do j=1,ntotpx-1440*(numdatarec)  !256
          recpx(j)=(bkgd-bzero)/bscale
        enddo

	    do k = 2,2*(ntotpx-1440*(numdatarec)),2
		  recdat(k)=recsw(k-1)
		  recdat(k-1)=recsw(k)
     	enddo
	    write(22,rec=nrec2) recdat
        close(22)
    end subroutine fits_prepro

      subroutine fits_superbkgd_pro(fitsfile,med_length,med_width,bkgdmode,enhance_flag,nfitsfile)
!       function:make superbkgd by self and complete the prepro（Not suitable for photometry）
!          input:fitsfile(fits file name)
!                med_length,med_width(the size of median filter window)
!                enhance_flag(enhance the image)
!         output:nfitsfile(new fits file name)
!           注意:可取消程序内注释输出超级背景图像nflatfile(new flat file name)
!			     当滤波窗口出现1时，自动执行两次滤波，med_length*med_width，med_width*med_length
        character*200 fitsfile,nflatfile,nfitsfile
        integer med_length,med_width,enhance_flag,bkgdmode
        integer *4 nmaxre,nbyf,npxf,i,bitpix,s
        integer*4 med_length0,med_width0
        parameter (nmaxre=15000,nbyf=2880,npxf=1440)
        integer *1 recdat(nbyf),recsw(nbyf)
        integer *2 recpx(npxf)
        equivalence (recsw,recpx)
        integer *4 naxis1,naxis2,npx,ntotpx,nrec,nrec2,seqnum
        character *2880 rhead
        parameter(maxheadrec=10)
        parameter(s=9500000)!from 9500000 to 200000000 for 4k*4k
        real*8 bzero,bscale,gain,fexptime,bexptime,dexptime,flexptime
        real*8 fitsdata(s),biasdata(s),darkdata(s),mdat_en(s)
        real*8 flatdata(s),nfitsdata(s),mdat(s),flatmean
		real*8 newmdat(s),newfmdat(s),bkgd,bkgdsigma,bkgd0,bkgdsigma0
		real*8 abox(3056,3056),abox2(3056,3056),ss(1000),abox3(3056,3056)

        open(5,file=fitsfile,status='old',access='direct',recl=nbyf)
     !   open(22,file=nflatfile,status='replace',access='direct',recl=nbyf) !output the new flat
   !zz   open(22,file=trim(nfitsfile)//'.flat.fit',status='replace',access='direct',recl=nbyf) !output the new flat
        open(23,file=nfitsfile,status='replace',access='direct',recl=nbyf)

        do i=1,maxheadrec
          read(5,rec=i) rhead
     !zz    write(22,rec=i) rhead  !output the new flat
          write(23,rec=i) rhead

          ic=index(rhead,'BITPIX  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),'(i21)') bitpix
          endif

          ic=index(rhead,'NAXIS1  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),'(i21)') naxis1
          endif

          ic=index(rhead,'NAXIS2  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),'(i21)') naxis2
          endif

          ic=index(rhead,'BSCALE  =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),*) bscale
          endif

          ic=index(rhead,'BZERO   =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),*) bzero
          endif

          ic=index(rhead,'EXPTIME =')
          if(ic.ne.0) then
            read(rhead(ic+9:ic+29),*) exptime
          endif

          ic=index(rhead,'END            ')
          if(ic.ne.0) then
            goto 93
          endif
        enddo
93      close(5)

        nrec=i+1
        nrec22=nrec
        nrec23=nrec
        mdat=0
        newmdat=0
        newfmdat=0
        mdat_en=0
        write(*,'(a,2i3)')     '              第一次~中值滤波窗口大小(length,width)：',med_length,med_width
        call fits_data(fitsfile,fitsdata,fexptime,npx)
        call cal_b(fitsdata,npx,bkgd0,bkgdsigma0)
        write(*,'(a,2f10.3)')  '          预处理前图像背景及sigma(image-bkgd,sigma)：',bkgd0,bkgdsigma0
        mdat=fitsdata
        newmdat=fitsdata!所有待处理图像均赋值为同原图，这样，避免边沿未修正的像素出现0或者1
        newfmdat=fitsdata
        mdat_en=fitsdata
!fitsdata(一维数组)数据序列变为行列的二维数组
        abox=1.0d0
        do i=1,npx
          call seq2mat(i,naxis1,naxis2,nli,nar)
          abox(nli,nar)=mdat(i)
          abox2(nli,nar)=mdat(i)!作为平场初始矩阵，后面滤波后会覆盖，边沿保留与原图像同
        enddo
        nmid=int((med_length*med_width)/2)+1!四舍五入
!中值滤波窗口为矩形时(建议奇数*奇数)
    if(med_length.gt.1 .and.med_width.gt.1) then
        do i=int(med_width/2)+1,naxis2-int(med_width/2)-1
          do j=int(med_length/2)+1,naxis1-int(med_length/2)-1
            k=1
			do i1=i-int(med_width/2),i+int(med_width/2)
				do j1=j-int(med_length/2),j+int(med_length/2)
				  ss(k)=abox(i1,j1)
				  k=k+1
				enddo
            enddo
            ns=k-1
            call shell_sort(ss,ns)
            abox2(i,j)=ss(nmid)!滤波后像素值
!中值滤波后的平场文件数据newfmdat
            call mat2seq(i,j,naxis1,naxis2,seqnum)
            newfmdat(seqnum)=abox2(i,j)
!若窗口不是条形，直接对原始图像做平场改正newmdat******************************************************
!20220718      if(dabs(newmdat(seqnum)).le.50000) then !保留亮晕中心过度像素
            if(dabs(mdat(seqnum)).ge.2) then !by zhang
!            if(med_length.gt.1 .and. med_width.gt.1)then
                if(bkgdmode==1)  newmdat(seqnum)=mdat(seqnum)/newfmdat(seqnum)*bkgd0!按照平场方法进行扣除
                if(bkgdmode==2)  newmdat(seqnum)=mdat(seqnum)-newfmdat(seqnum)+bkgd0!按照直接相减方法进行扣除
!                if(bkgdmode.gt.2) print*,'Please confirm the bkgdmode setting!'
!            endif
        else
                newmdat(seqnum)=abox2(i,j)
 !20220718       endif
      endif  !结束非条形if判断
          enddo
        enddo
    endif
        call cal_b(newmdat,npx,bkgd,bkgdsigma) !计算新图像的背景和背景sigma，若条形则为原图结果
!=================结束矩形处理
!=================若为条形窗口，进行以下处理
!若窗口明显为条形(?*1 or 1*?)，横竖两次滤波(仅一次)
    if(med_length.eq.1 .or. med_width.eq.1)then
!第一次行处理
        do i=int(med_width/2)+1,naxis2-int(med_width/2)-1
          do j=int(med_length/2)+1,naxis1-int(med_length/2)-1
            k=1
			do i1=i-int(med_width/2),i+int(med_width/2)
				do j1=j-int(med_length/2),j+int(med_length/2)
				  ss(k)=abox(i1,j1)
				  k=k+1
				enddo
            enddo
            ns=k-1
            call shell_sort(ss,ns)
            abox2(i,j)=ss(nmid)!滤波后像素值
!中值滤波后的平场文件数据newfmdat
            call mat2seq(i,j,naxis1,naxis2,seqnum)
            newfmdat(seqnum)=abox2(i,j)
!对原始图像做平场改正newmdat******************************************************
!20220718      if(dabs(newmdat(seqnum)).le.50000) then
         if(dabs(mdat(seqnum)).ge.2) then !by zhang
                if(bkgdmode==1)  newmdat(seqnum)=mdat(seqnum)/newfmdat(seqnum)*bkgd0!按照平场方法进行扣除
                if(bkgdmode==2)  newmdat(seqnum)=mdat(seqnum)-newfmdat(seqnum)+bkgd0!按照直接相减方法进行扣除
                if(bkgdmode.gt.2) print*,'Please confirm the bkgdmode setting!'
         else
                newmdat(seqnum)=abox2(i,j)
        endif
!20220718     endif
          enddo
        enddo
        call cal_b(newmdat,npx,bkgd,bkgdsigma)
        write(*,'(a,2f10.3)')  '    第一次滤波后的图像背景及sigma(image-bkgd,sigma)：',bkgd,bkgdsigma
!第一次行处理结束
!第二次列处理-----
           med_width0=med_length
           med_length0=med_width
        write(*,'(a,2i3)')     '              第二次~中值滤波窗口大小(length,width)：',med_length0,med_width0
        do i=1,npx
          call seq2mat(i,naxis1,naxis2,nli,nar)
	      abox(nli,nar)=newmdat(i)
         abox2(nli,nar)=newmdat(i)!作为平场初始矩阵，后面滤波后会覆盖，边沿保留与原图像同
        enddo
        do i=int(med_width0/2)+1,naxis2-int(med_width0/2)-1
            do j=int(med_length0/2)+1,naxis1-int(med_length0/2)-1
                k=1
                do i1=i-int(med_width0/2),i+int(med_width0/2)
                    do j1=j-int(med_length0/2),j+int(med_length0/2)
                        ss(k)=abox(i1,j1)
                        k=k+1
                    enddo
                enddo
                ns=k-1
                call SHELL_SORT(ss,ns)
                abox2(i,j)=ss(nmid)!滤波后像素值 ，滤波的像素，未滤波的同前面平场图
!中值滤波后的平场文件数据newfmdat
                call mat2seq(i,j,naxis1,naxis2,seqnum)
                newfmdat(seqnum)=abox2(i,j)
!20220718            if(dabs(newmdat(seqnum)).le.50000) then
                if(dabs(newmdat(seqnum)).ge.2) then
                   if(bkgdmode==1)  newmdat(seqnum)=newmdat(seqnum)/newfmdat(seqnum)*bkgd0!按照平场方法进行扣除
                   if(bkgdmode==2)  newmdat(seqnum)=newmdat(seqnum)-newfmdat(seqnum)+bkgd0!按照直接相减方法进行扣除
                   if(bkgdmode.gt.2) print*,'Please confirm the bkgdmode setting!'
                else
                   newmdat(seqnum)=abox2(i,j)
                endif
!20220718            endif
            enddo
        enddo
        call cal_b(newmdat,npx,bkgd,bkgdsigma)
        write(*,'(a,2f10.3)')  '    第二次滤波后的图像背景及sigma(image-bkgd,sigma)：',bkgd,bkgdsigma
!第二次列处理结束-----
!选择是否图像增强：
     endif
       mdat_en=newmdat
       if(enhance_flag.eq.1)then
          call fits_enhance(newmdat,naxis1,naxis2,mdat_en)
          call cal_b(mdat_en,npx,bkgd,bkgdsigma)
          write(*,'(a,2f10.3)') '     3*3均值滤波后图像背景及sigma(image-bkgd,sigma)：',bkgd,bkgdsigma
       endif
!  写生成的新平场文件newflatfits************************
        npx=1
		ntotpx=naxis1*naxis2
        numdatarec=int(ntotpx*bitpix/8/nbyf)
        do i=1,numdatarec
          do j = 1,npxf
            recpx(j)=(newfmdat(npx)-bzero)/bscale
            npx = npx + 1
          enddo
          do k = 2,2880,2
            recdat(k)=recsw(k-1)
            recdat(k-1)=recsw(k)
          enddo
       !zz   write(22,rec=nrec22) recdat  !output new flat
        nrec22=nrec22+1  !output new flat
        enddo
!zz        close(22)   !output new flat
!    print*,'写新flat文件结束'!output new flat
!  写生成的新fits文件（newfits）************************
        npx=1
        do i=1,numdatarec
          do j = 1,npxf
            recpx(j)=(mdat_en(npx)-bzero)/bscale
            npx = npx + 1
          enddo
          do k = 2,2880,2
            recdat(k)=recsw(k-1)
            recdat(k-1)=recsw(k)
          enddo
          write(23,rec=nrec23) recdat
          nrec23=nrec23+1
        enddo
!补充剩余像素2019-10-11
!      write(*,*) ntotpx-1440*(numdatarec)
        do j=1,ntotpx-1440*(numdatarec)  !256
          recpx(j)=(bkgd-bzero)/bscale
        enddo

	    do k = 2,2*(ntotpx-1440*(numdatarec)),2
		  recdat(k)=recsw(k-1)
		  recdat(k-1)=recsw(k)
     	enddo
	    write(23,rec=nrec23) recdat
        close(23)

        end subroutine fits_superbkgd_pro


      subroutine seq2mat(seqnum,naxis1,naxis2,nli,nar)
!       function:Calculate the column Numbers in the matrix
!          input:seqnum:sequence number
!                naxis1,naxis2:The size of the matrix
!         output:nli,nar：column Numbers in the matrix(naxis1,naxis2)
! nli--n_line;nar-n_arrager
        implicit real*8(a-h,o-z)
        integer seqnum,naxis1,naxis2,nli,nar,dd

        if(mod(seqnum,naxis1).eq.0) then
          nli=int(seqnum/naxis1)
        else
          nli=int(seqnum/naxis1)+1
        endif
        nar=seqnum-(nli-1)*naxis1
        end subroutine seq2mat

      subroutine mat2seq(nli,nar,naxis1,naxis2,seqnum)
!       function:Calculate the sequence Numbers in the matrix
!          input:nli,nar：column Numbers in the matrix(naxis1,naxis2)
!                naxis1,naxis2:The size of the matrix
!         output:seqnum:sequence number
! nli--n_line;nar-n_arrager
        implicit real*8(a-h,o-z)
        integer seqnum,naxis1,naxis2,nli,nar

        seqnum=naxis1*(nli-1)+nar
        end subroutine mat2seq

      subroutine cal_b(mdat,npx,bkgd,bkgdsigma)
!       function:calculate the background and bkgdsigma of fits
!          input:mdat：fitsdata
!                npx:the size of the mdat
!         output:bkgd:the average of fitsdata
!                bkgdsigma:Background relief
!注意：背景值为扣除>2.6sigma后两个sigma差异不大才为背景与sigma值
!      这样就避免了图像中星象的影响，仅为背景值和背景起伏
        implicit real*8(a-h,o-z)
        real*8 mdat(npx),bkgd,bkgdsigma
        parameter(sfa=2.6d0)
        integer k,nstep

        nstep=1
        k=1
        sumvalue=0.0d0
        do i=1,npx,nstep
          sumvalue=sumvalue+mdat(i)
          k=k+1
        enddo
        avervalue=sumvalue/real(k-1)
        sumvalue2=0.0d0
        do i=1,npx,nstep
          sumvalue2=sumvalue2+(mdat(i)-avervalue)**2
        enddo
        sigma=dsqrt(sumvalue2/(k-1-1))
!  计算像素值-平均值，若小于2.6sigma计入背景值，大于则不计入
10      sumvalue=0.0d0
        k=1
        do i=1,npx,nstep
          temp=mdat(i)-avervalue
          if(dabs(temp).le.sfa*sigma) then
            sumvalue=sumvalue+mdat(i)
            k=k+1
          endif
        enddo
        avervalue2=sumvalue/(k-1)
        sumvalue2=0.0d0
        do i=1,npx,nstep
          temp=mdat(i)-avervalue
          if(dabs(temp).le.sfa*sigma) then
            sumvalue2=sumvalue2+(mdat(i)-avervalue2)**2
          endif
        enddo
        sigma2=dsqrt(sumvalue2/(k-1-1))

        if(sigma2.le.1d-6) then
 !        print*,'图像较为平坦(bkgd,sigma):',avervalue,sigma
          goto 20
        endif

        if(dabs(sigma2-sigma).ge.0.01*sigma2) then
!         print*,'图像不平坦(bkgd,sigma):',avervalue,sigma
          avervalue=avervalue2
          sigma=sigma2
          goto 10
        endif
! 认为如果两者差异不大，则第一次计算可代表整幅图平均和平坦度。
! 一般均需迭代5次左右
20      bkgd=avervalue
        bkgdsigma=sigma
        end subroutine cal_b


     subroutine shell_sort(A,N)
!       function:reorder the A sequence
!          input:A:old sequence
!                N:the size of A
!         output:A:new sequence
!注意：排序算法有些慢，有待优化
     implicit none
     integer :: N
     real*8 A(N) ! 传入的数据
     integer I,J,B(N)       ! 循环计数器
     real*8 TEMP      ! 交换数值用
     integer K,TEMP02         ! K 值

     K=N/2             ! K 的初值
     do while( K>0 )
    	do I=K+1,N
        	J=I-K
        	do while( J>0 )
! 如果A(J)>A(J+K),要交换它们的数值,并往回取出
! A(J-K)、A(J)为新的一组来比较。
        		if ( A(J) .GT. A(J+K) ) then
          			TEMP=A(J)
          			A(J)=A(J+K)
          			A(J+K)=TEMP

          			J=J-K
        		else
          			exit ! A(J)<A(J+K)时可跳出循环
        		end if
        	end do
      	end do
      	K=K/2 ! 设定新的K值
      end do
      return
     end subroutine shell_sort

     subroutine fits_enhance(mdat,naxis1,naxis2,mdat_en)
!       function:enhance the fits image
!          input:mdat:the fitsdata
!                naxis1,naxis:the size of mdat
!         output:mdat_en:the new fitsdata
!注意：算法：九宫格中心像素值=9个像素值求平均，均值滤波
!图像增强，2019-09-19,by zhanghuiyan
    real*8 mdat(9500000),mdat_en(9500000)
    integer*4 naxis1,naxis2,npx,seq0,seq,nli,nar
    integer*4 i,j,i1,j1

    do i=2,naxis2-1
        do j=2,naxis1-1
            sum=0
            do i1=-1,1
                    nli=i+i1
                do j1=-1,1
                    nar=j+j1
                    call mat2seq(nli,nar,naxis1,naxis2,seq)
                    sum=sum+mdat(seq)
                enddo
            enddo
            call mat2seq(i,j,naxis1,naxis2,seq0)
            mdat_en(seq0)=sum/9.0
        enddo
    enddo
    end subroutine fits_enhance
