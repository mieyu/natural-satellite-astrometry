! **********************************CCD Image preprocessing*************************************
!program name:02detect.f90
! function:1）逐幅检测星象，并计算其中心位置
!          2) 生成*.reg文件，并输出检测星象的位置和亮度信息
!    input:0）(注意根据图像不同，调用fits_header时需注意时间。目前已经修改，如果标准头，本程序不依赖文件曝光开始结束时刻的格式)
!          1) 配置文件信息（adias.cfg）
!             1.1）背景起伏阈值系数：2bkgd_threshold=5.0
!             1.2）信噪比阈值：2snr_threshold=5.0 
!             1.3）星象中心定位的方法：2pos_method=2（1-修正矩；2-二阶修正矩；3-三阶修正矩）
!   output:1）检测星象文件：*.reg
    
!  子程序：1）fits_header(fitsfile,bitpix,naxis1,naxis2,bscale,bzero,gain,exptime,year,month,day,hh,mm,ss)
!                      获取fits图像头文件信息（注意不同图像头文件时间信息的不同）
!          2) fits_data(fitsfile,fitsdata,exptime,npx)
!                      获取fits图像数据（已增加对非整块像素的读取）
!          3) detect_xzj(fitsfile,bkgd_threshold,sumi,starx,stary,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma)
!                      连通域检测星象+修正矩定星象中心
!          4) detect_guass(fitsfile,bkgd_threshold,sumi,starxx,staryy,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma)
!                      连通域检测星象+高斯定星象中心
!          5) cal_b(mdat,npx,bkgd,bkgdsigma)
!                      计算fits图像背景值及其sigma（已扣除星象影响）
!          6) sorting_7terms(x01,x02,x03,x04,x05,x06,x07,n)
!                      以x01为参考，对数列进行排序
!          7) seq2mat(seqnum,naxis1,naxis2,nli,nar) 
!                      一维数组变为二维数组
!          8) mat2seq(nli,nar,naxis1,naxis2,seq) 
!                      二维数组变为一维数组
!          9) 高斯相关子程序（待补充）目前单次计算高斯位置可用，精度不如修正矩。多次迭代待优化
!注意：若在之前的pre程序中使用了超级背景图像的方法做预处理，这里的结果不能用于测光目的使用
! by zhy 2019.09.02
! V2.2 add the enhance function by zhy 2019.09.24
! V3.0  Chinese comment by zhy 2020.01.29
!20200212修改信噪比公式，使得信噪比=所有像素-背景值/起伏度
!20200216修改detect_xzj子程序，将亮度输出为原始图像亮度，没有减过背景的数据，方便在match部分计算夜天光
!20200216亮度输出为原始图像-背景（含了bias）数值
!20241001 修改过程输出为中文
    
      program detect
       implicit real*8(a-h,o-z)
       parameter(m=2000)
       integer pos_method
	   real*8 bkgd_threshold,snr_threshold
	   integer*4 ic,ic1,nstar,i,n_fits,n_outstar,flatflag,superflag
       character*200 tempcha,fitspath,fitsfile0,fitsfile,xyfile
       real*8 gain,bkgd,bkgdsigma
	   real*8 sumi(50000),starx(50000),stary(50000),snr(50000)
       integer*4 star_id(50000),star_pix(50000),overflag(50000)
       integer*4 n_day
       character*100 tele_label

!01--读配置文件       
      open(1,file='fitspath.in',status='old')
!        open(1,file='D:\00adias\exe\fitspath.in',status='old')

       n_day=0
77     read(1,'(a100)',end=777) fitspath
       fitspath=trim(fitspath)

       n_day=n_day+1   !用以记录共处理几天数据
       write(*,'(a,i3.3,a,a,a)')'第', n_day,'天-','本日fits所在文件夹：',trim(fitspath)
       write(*,*)'    检测出的星象的信息已写入reg文件，可供后续程序调用及DS9显示！'
       write(*,*)'    ====================本日fits图像处理情况==================='
       write(*,*)
    
!按照fitspath.in的配置文件内容开始逐日处理图像   
     open(11,file='adias.cfg')
!     open(11,file='D:\00adias\exe\adias.cfg')
      do i=1,m
	      read(11,'(a100)',end=1000) tempcha

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
          
	      ic=index(tempcha,'2bkgd_threshold=') 
	      if(ic.gt.0) then
  	      ic1=index(tempcha,'=')
	        read(tempcha(ic1+1:ic1+10),*) bkgd_threshold
          endif
          
	      ic=index(tempcha,'2snr_threshold=') 
	      if(ic.gt.0) then
  	      ic1=index(tempcha,'=')
	        read(tempcha(ic1+1:ic1+10),*) snr_threshold
          endif   
        
	      ic=index(tempcha,'2pos_method=') 
	      if(ic.gt.0) then
  	      ic1=index(tempcha,'=')
	        read(tempcha(ic1+1:ic1+10),*) pos_method
          endif          

      enddo
1000  close(11)		
!
!02--逐幅读取图像（*_n.fit），进行星象检测
      open(11,file=trim(fitspath)//'/'//'fits.lst')
      do n_fits=1,m   
        read(11,'(a100)',end=999) fitsfile0	  
           write(*,'(a,i4.4,2a)') '  ',n_fits,'-',trim(fitsfile0)
           xyfile=trim(fitsfile0)//'.reg'
           open(15,file=xyfile)
           write(15,'(a)') 'global color=green font="helvetica 10 normal" selec&
           &t=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source' 
           write(15,'(a)') 'physical'
!
!==========连通域检测+修正矩方法定星象中心
           call detect_xzj_yy(flatflag,superflag,fitsfile0,bkgd_threshold,pos_method,sumi,starx,stary,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma) 
          ! call detect_xzj_zz(flatflag,superflag,fitsfile0,bkgd_threshold,pos_method,sumi,starx,stary,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma) 
!==========连通域检测+高斯方法定星象中心(暂不可用)
!           call detect_gauss(fitsfile,bkgd_threshold,sumi,starx,stary,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma)

           n_outstar=0   !统计满足snr条件的星数
           do i=1,nstar
             if(snr(i).gt.snr_threshold .and.star_pix(i).gt.5)then
                write(15,'(a7,2f11.3,2f6.1,a5,f21.4,f10.2,3i5,2f15.3)')& 
                &     'ellipse',starx(i),stary(i),real(10),real(10),&
                &     '  #  ',sumi(i),snr(i),star_id(i),star_pix(i),overflag(i),bkgd,bkgdsigma
                n_outstar=n_outstar+1
             endif
           enddo   
           write(*,'(a,2f10.3)')  '                    图像的背景及sigma: ',bkgd,bkgdsigma          
           write(*,'(a,i4)'),     '    满足SNR和最少像素数条件的检测星数: ',n_outstar
           write(*,*)
           close(15)            
      enddo
999   close(11)

!03--屏幕输出信息
      write(*,'(a)')   '================02Detect-Program execution summary=================='
      write(*,'(a,i4)')'    完成星象检测(*.reg)，共检测图像：',n_fits-1
      write(*,'(a)')   '    检测出的星象信息已写入.reg文件（存储于图像文件夹，可供DS9加载使用）'
      write(*,'(a)')   '===================================================================='    

!处理下一天数据
    goto 77
777 close(1)
    write(*,'(a,i3)') '星象检测程序结束，共检测图像天数：',n_day
    write(*,'(a)')    '================================================================='
    end program detect   
!*********************************************************************************

    
!=========================subtoutine==========================               
      subroutine detect_xzj_yy(flatflag,superflag,fitsfile0,bkgd_threshold,pos_method,sumi_real,starx,stary,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma)
!       function:detect stars and output the stars center
!          input:fitsfile:fits file name
!                bkgd_threshold:fitsdata-bkgd_threshold*bkgdsigma
!         output:sumi:the stars' flux
!                starx:the x-position of star center
!                stary:the x-position of star center
!                snr:the stars' snr
!                star_id:the id of the star( already sorted by brightness)
!                star_pix:The number of stars contained in star
!                overflag:Whether the stars overflow
!                nstar:Number of detected stars
!                bkgd:the image bkgd
!                bkgdsigma:the image bkgd
!Note:最大目标数量=naxis1*naxis2/pi/6**2  含最大像素数=pi*15**2, minpix=3
      implicit none
      character*200 fitsfile,fitsfile0 
      integer pos_method
      integer*4 i,j,naxis1,naxis2,npx,bitpix,s,seq0,seq1,k,flatflag,superflag
      integer*4 maxobj,minpix,maxpix,nli,nar,nstar,pos_nstar,npx0
      real*8 bzero,bscale,gain,bkgd,bkgdsigma,bkgd_threshold,bkgd0,bkgdsigma0
      parameter(s=9000000)
      real*8 mdat(s),mdat01(s),abox(3000,3000),lty(4),mdat0(s),abox0(3000,3000)
	  real*8 sumx(50000),sumy(50000),maxflux
      real*8 starx(50000),stary(50000),sumi(50000),pi,exptime,ss,sumi_real(50000)
      integer*4 star_id(50000),star_pix(50000),overflag(50000)
	  real*8 snr(50000),snr01(50000)  
      integer*4 idpix(s),numpix(s),objpos(5000,5000)
      integer*4 numobj,ic,ic1
      
      integer idbox(3000,3000),idbox2(3000,3000),nr,ni1,ni2,nj1,nj2,kread,iflag,i1,j1,neid,eid1(50000),eid2(50000),tempeid1,tempeid2
      character*300 tempcha1(50000),tempchap 
      
!      nstar=0
      pi=4*datan(1.0d0)
      bkgd=0.0d0
      bkgdsigma=0.0d0
      idbox2=0
      idbox=0
      if((flatflag+superflag).lt.0.5)then
        fitsfile=fitsfile0
        write(*,'(a,i5)') '使用原始图像进行图像检测！'
      else
        ic=index(fitsfile0,'.fit') 
        if(ic.gt.0) then
           ic1=index(fitsfile0,'.fit') 	    
 	       fitsfile0=trim(fitsfile0)
	       fitsfile=fitsfile0(1:ic1-1)//'_n.fit'
        endif
      endif
!读取fits头文件及数据信息，并确定最大目标数maxobj、最大星象含像素数maxpix及溢出maxflux          
!最大目标数：假设视场中全是半径为6的星象，如ex: 1024*1056/3.1415/6/6=9561，实际是没有这么多的
!最大星象含像素数则是，定义半径为15的星象所含像素数，一般没有这么大的星象，最大半径仅5左右
      call fits_header_main(fitsfile,bitpix,naxis1,naxis2,bscale,bzero,gain,exptime)

      if(dabs(gain).le.1e-9) gain=1.0    
      maxflux=2**bitpix-1
!      maxflux=62000  !tong yu
      maxobj=int(naxis1*naxis2/pi/6**2)        
      minpix=3
      maxpix=int(pi*40**2)
      call fits_data(fitsfile,mdat,exptime,npx) 
      call cal_b(mdat,npx,bkgd,bkgdsigma)   !the whole image 
     ! call fits_data(fitsfile0,mdat0,exptime,npx0) !为了调用原始图像亮度，目前不用
     ! call cal_b(mdat0,npx0,bkgd0,bkgdsigma0)   !为了调用原始图像亮度，目前不用      
      
!连通域标号前对数据进行处理
!each pixes ADU-（background＋bkgd_threshold*bkgdsigma）！bkgd_threshold一般设5，因图像预处理过（包含增强），sigma较小
!若未预处理，sigma建议设置为2.6或者3
      do i=1,npx
        mdat01(i)=mdat(i)-(bkgd+bkgd_threshold*bkgdsigma)
        if(mdat01(i).le.0.0d0) mdat01(i)=0.0d0
      enddo 
      abox=0.0
      do i=1,npx
        call seq2mat(i,naxis1,naxis2,nli,nar)    
        abox(nli,nar)=mdat01(i)
        abox0(nli,nar)=mdat(i)
      enddo
!set the image edge pixel data =0
      do i=1,naxis1
        abox(i,1)=0.0d0
        abox(i,naxis2)=0.0d0
      enddo
      do j=1,naxis2
        abox(1,j)=0.0d0
        abox(naxis1,j)=0.0d0
      enddo
      
!八邻域连通检测，对每像素标号
!lty1=右上，lty2=正上，lty3=左上，lty4=左
!目标号：numobj；像素标号idpix(numobj)=numobj,目标含像素数numpix(numobj)
!从上至下，从左至右逐个像素检测，当某像素>0时，分别做如下判断：
!1)其4邻均<0则：新建目标numobj+1，该目标像素数numpix(numobj)+1，该像素标号idpix(seq)=numobj
!2）lty1>0则：1的标号给当前像素，目标像素数+1
!3）lty2>0则：2的标号给当前像素，目标像素数+1
!4）lty3>0则：3的标号给当前像素，目标像素数+1
!5）lty4>0则：4的标号给当前像素，目标像素数+1
!maxobj设定检测目标数最大=全像素/孔径面积，若超过，结束标号并输出提示
!maxpix目标含像素数最多=2倍孔径圆像素,若超过，输出提示
!八连通域标号一次即可，不需要重复标号，不会出现重复编号
!编号原则：先扫描上一行3像素，有则设置同，再看左边同行，有则设置同，共计4个像素
      numobj=0
      numpix=0
      idpix=0
      objpos=0
      do i=2,naxis1-1  !行
        do j=2,naxis2-1  !列
          lty(1)=abox(i-1,j+1)
          lty(2)=abox(i-1,j)
          lty(3)=abox(i-1,j-1)
          lty(4)=abox(i,j-1)
          if(abox(i,j).gt.1d-9) then
            call mat2seq(i,j,naxis1,naxis2,seq0)
!星象只有一个像素，其余均0
            if(dabs(lty(1)+lty(2)+lty(3)+lty(4)).le.1d-9) then
              numobj=numobj+1
              idbox(i,j)=numobj
              idpix(seq0)=numobj !像素标号
              numpix(numobj)=numpix(numobj)+1  !目标累计像素
              objpos(idpix(seq0),numpix(numobj))=seq0

              !if(numobj.gt.maxobj) then
                !write(*,*)'Detect stars more than maxobj:',numobj,maxobj
                !write(*,*)'Warning:Image quality problem!'
                !pause
                !goto 953
              !endif
              !if(numpix(numobj).gt.maxpix) then
                !write(*,*)'Pixels of star more than maxpix:',numpix(numobj),maxpix
                !write(*,*)'Warning:please check the radius value (maybe too small)!'
                !pause
                !goto 952
              !endif                  
! 右上
            elseif(lty(1).gt.1d-9) then
              call mat2seq(i-1,j+1,naxis1,naxis2,seq1)            
	          idbox(i,j)=idbox(i-1,j+1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0

              !if(numpix(idpix(seq0)).gt.maxpix) then
                !write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                !write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                !goto 952
              !endif    
! 正上
            elseif(lty(2).gt.1d-9) then
	          idbox(i,j)=idbox(i-1,j)
              call mat2seq(i-1,j,naxis1,naxis2,seq1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0

              !if(numpix(idpix(seq0)).gt.maxpix) then
                !write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                !write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                !goto 952
              !endif     
! 左上         
            elseif(lty(3).gt.1d-9) then
	          idbox(i,j)=idbox(i-1,j-1)
              call mat2seq(i-1,j-1,naxis1,naxis2,seq1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0
              !if(numpix(idpix(seq0)).gt.maxpix) then
                !write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                !write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                !goto 952
              !endif     
! 左边      
            elseif(lty(4).gt.1d-9) then
	          idbox(i,j)=idbox(i,j-1)
              call mat2seq(i,j-1,naxis1,naxis2,seq1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0
              !if(numpix(idpix(seq0)).gt.maxpix) then
                !write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                !write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                !goto 952
              !endif
            endif
          endif
952     enddo  !952 'this image includes super star(>pi*r^2)'
      enddo
! ========================结束连通域标号
953 continue   
    
      nr=250
      idbox2=idbox
      do i=2,naxis2-1
	  do j=naxis1-1,2,-1

        if(abox(i,j).gt.1d-9.and.abox(i,j-1).gt.1d-9) then
	      if(idbox2(i,j).eq.idbox2(i,j-1)) then
			  goto 9522
	      else 
              ni1=i-nr
              if(ni1.le.1) ni1=1
              ni2=i+nr
              if(ni2.ge.naxis2) ni2=naxis2
              nj1=j-nr
              if(nj1.le.1) nj1=1
              nj2=j+nr
              if(nj2.ge.naxis1) nj2=naxis1
              
              k=1
              do i1=ni1,ni2
                do j1=nj1,nj2
                
                  if((idbox2(i1,j1).eq.idbox2(i,j-1)).and.(i1.ne.i.and.j1.ne.j-1)) then
                    idbox2(i1,j1)=idbox2(i,j)
                    k=k+1
                  endif
                enddo
              enddo       
              idbox2(i,j-1)=idbox2(i,j)
              
            endif	          
          endif	        
9522    enddo
      enddo

!  建立等价表2017.9.8
      open(333,file='fort.333',status='replace')
      open(334,file='fort.334',status='replace')
      open(335,file='fort.335',status='replace')
      open(336,file='fort.336',status='replace')

      do i=2,naxis2-1
        do j=2,naxis1-1
          if(abox(i,j).gt.1d-9) then
            
            if(idbox2(i,j).ne.idbox2(i,j-1).and.idbox2(i,j-1).gt.0) then
              if(idbox2(i,j).lt.idbox2(i,j-1)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i,j-1)
              else
                write(333,'(2i10)') idbox2(i,j-1),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i,j+1).and.idbox2(i,j+1).gt.0) then
              if(idbox2(i,j).lt.idbox2(i,j+1)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i,j+1)
              else
                write(333,'(2i10)') idbox2(i,j+1),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i-1,j-1).and.idbox2(i-1,j-1).gt.0) then
              if(idbox2(i,j).lt.idbox2(i-1,j-1)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i-1,j-1)
              else
                write(333,'(2i10)') idbox2(i-1,j-1),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i-1,j).and.idbox2(i-1,j).gt.0) then
              if(idbox2(i,j).lt.idbox2(i-1,j)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i-1,j)
              else
                write(333,'(2i10)') idbox2(i-1,j),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i-1,j+1).and.idbox2(i-1,j+1).gt.0) then
              if(idbox2(i,j).lt.idbox2(i-1,j+1)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i-1,j+1)
              else
                write(333,'(2i10)') idbox2(i-1,j+1),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i+1,j-1).and.idbox2(i+1,j-1).gt.0) then
              if(idbox2(i,j).lt.idbox2(i+1,j-1)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i+1,j-1)
              else
                write(333,'(2i10)') idbox2(i+1,j-1),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i+1,j).and.idbox2(i+1,j).gt.0) then
              if(idbox2(i,j).lt.idbox2(i+1,j)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i+1,j)
              else
                write(333,'(2i10)') idbox2(i+1,j),idbox2(i,j)
              endif 
            endif

            if(idbox2(i,j).ne.idbox2(i+1,j+1).and.idbox2(i+1,j+1).gt.0) then
              if(idbox2(i,j).lt.idbox2(i+1,j+1)) then
                write(333,'(2i10)') idbox2(i,j),idbox2(i+1,j+1)
              else
                write(333,'(2i10)') idbox2(i+1,j+1),idbox2(i,j)
              endif 
            endif
          endif
        enddo
      enddo

      rewind(333)

!  去重复1
      k=1
      kread=0
      read(333,'(a20)',end=93) tempcha1(k)
      kread=kread+1

      do i=2,naxis1*naxis2
        read(333,'(a20)',end=93) tempchap
        iflag=0
        do j=1,k
          if(tempchap.eq.tempcha1(j)) iflag=1
        enddo 

        if(iflag.eq.0) then
          k=k+1
          tempcha1(k)=tempchap
        endif
      enddo
93    close(333)

      if(kread.eq.0) then
        close(334)
        close(335)
        close(336)
        neid=0
        goto 88
      endif

      do i=1,k
        write(334,'(a20)')  tempcha1(i)
      enddo

      rewind(334)
      
      k=1
      read(334,*,end=92) eid1(k),eid2(k)
      write(335,'(2i10)') eid1(k),eid2(k)
      do i=2,naxis1*naxis2
        read(334,*,end=92) tempeid1,tempeid2
        do j=1,k
          if(tempeid1.eq.eid2(j)) then
            tempeid1=eid1(j)
            goto 91
          elseif(tempeid2.eq.eid2(j)) then
            tempeid2=tempeid1
            tempeid1=eid1(j)
            goto 91
          endif
        enddo
91      k=k+1
        eid1(k)=tempeid1
        eid2(k)=tempeid2
        write(335,'(2i10)') eid1(k),eid2(k)
      enddo
92    close(334)

!  去重复2
      rewind(335)
      k=1
      read(335,'(a20)',end=932) tempcha1(k)

      do i=2,naxis1*naxis2
        read(335,'(a20)',end=932) tempchap
        iflag=0
        do j=1,k
          if(tempchap.eq.tempcha1(j)) iflag=1
        enddo 

        if(iflag.eq.0) then
          k=k+1
          tempcha1(k)=tempchap
        endif
      enddo
932    close(335)

      do i=1,k
        write(336,'(a20)')  tempcha1(i)
      enddo

      rewind(336)
      do i=1,naxis1*naxis2
        read(336,*,end=90) eid1(i),eid2(i)
      enddo
90    neid=i-1
      close(336)
!      write(*,*) neid,eid2(1:neid)
88    continue
      
      	do i=2,naxis2-1
        do j=2,naxis1-1  
          if(abox(i,j).gt.1d-9) then
            do k=1,neid
              if(idbox2(i,j).eq.eid2(k)) idbox2(i,j)=eid1(k)
            enddo
          endif
        enddo
      enddo
    
    
!! ===================XZJ
!!compute the center of the object
! starx(k):x-value
! stary(k):y-value
! stari(k):flux-value（mdat01---has subtracted (bkgd+bkgd_threshold*bkgdsigma),not final value）！！
!注意，此处使用像素灰度值为mdat01(i)=mdat(i)-(bkgd+bkgd_threshold*bkgdsigma)
      k=1
      sumx=0.0
      sumy=0.0 
      sumi=0.0
      sumi_real=0.0
      starx=0.0
      stary=0.0  
      numpix=0

!边界星像不输出，四边各扣除10个像素
      do i=10,naxis2-10
        do j=10,naxis1-10
          if(idbox2(i,j).gt.0) then !.and.abox0(i,j).lt.maxflux) then !20220718处理云台1m天卫数据--曝光过度依然计算星象中心
              sumx(idbox2(i,j))=sumx(idbox2(i,j))+j*abox(i,j)**pos_method
              sumy(idbox2(i,j))=sumy(idbox2(i,j))+i*abox(i,j)**pos_method
              sumi(idbox2(i,j))=sumi(idbox2(i,j))+abox(i,j)**pos_method
              sumi_real(idbox2(i,j))=sumi_real(idbox2(i,j))+abox(i,j)
              numpix(idbox2(i,j))=numpix(idbox2(i,j))+1
          endif  
          if(abox0(i,j).ge.maxflux) overflag(idbox2(i,j))=1
        enddo
      enddo
            
!!!!!!!!!!!!!!!!2021-8-31      
      k=1
      
      do i=1,numobj
        if(numpix(i).ge.minpix.and.numpix(i).le.maxpix.and.overflag(i).lt.1) then

	      starx(k)=sumx(i)/sumi(i)
	      stary(k)=sumy(i)/sumi(i)
          sumi_real(k)=sumi_real(i)
          star_pix(k)=numpix(i)
          star_id(k)=i
          snr(k)=sumi_real(i)/dsqrt(sumi_real(i)+numpix(i)*bkgdsigma**2)

          k=k+1
            
            
!          do j=1,numpix(i)
!            call seq2mat(objpos(i,j),naxis1,naxis2,nli,nar)  
!            if(mdat01(objpos(i,j)).gt.maxflux) overflag(k)=1
!            sumx(k)=sumx(k)+nar*mdat01(objpos(i,j))**pos_method
!            sumy(k)=sumy(k)+nli*mdat01(objpos(i,j))**pos_method
!            sumi(k)=sumi(k)+mdat01(objpos(i,j))**pos_method 
!           ! sumi_real(k)=sumi_real(k)+(mdat0(objpos(i,j))-bkgd0)!用于输出亮度
!           sumi_real(k)=sumi_real(k)+mdat(objpos(i,j))
!          enddo
!maxim software:snr=sumi/bkgdsima/sqrt(pi*radius1**2)
!yuyong:tempsnrflux=sumvalue/dsqrt(sumvalue+numpix1*(bkgdsigma**2))
!tang:snr=mdat(i)-bkgd/bkgdsigma
          !snr(k)=sumi_real(k)/(bkgdsigma0*numpix(i)) 
          !snr(k)=(sumi_real(k)-bkgd*numpix(i))/(bkgdsigma*numpix(i)) ！zhang直接定义（扣除了bias影响）
          ! sumi_real(k)=sumi_real(k)-numpix(i)*bkgd
          ! snr(k)=(sumi_real(k)-bkgd*numpix(i))/bkgdsigma 
!          snr(k)=sumi_real(k)/sqrt(sumi_real(k)+numpix(i)*(bkgdsigma**2)) !yuyong 考虑了星象的噪声（泊松分布）
!          starx(k)=sumx(k)/sumi(k)
!          stary(k)=sumy(k)/sumi(k)
!          star_id(k)=i
!          star_pix(k)=numpix(i)
!          k=k+1
        endif
      enddo 
      nstar=k-1
!修正矩定星象中心结束
!对星象按亮度排序
      call sorting_7terms(sumi_real,starx,stary,snr,star_id,star_pix,overflag,nstar)
      
      call system('del fort.333')
      call system('del fort.334')
      call system('del fort.335')
      call system('del fort.336')
      
    end subroutine detect_xzj_yy

    
      subroutine fits_header_main(fitsfile,bitpix,naxis1,naxis2,bscale,bzero,gain,exptime)
!         function:get the fits header information
!            input:fitsfile(fits file name)
!           output: bitpix:image 
!                   naxis1/2:image size
!                   bscale:
!                   bzero:
!                   gain:
!                   exptime:
     implicit real*8(a-h,o-z)
       parameter(maxheadrec=10)   
       integer*4 naxis1,naxis2,nmaxre,nbyf,npxf,i,bitpix
       parameter (nmaxre=15000,nbyf=2880,npxf=1440)
       character*200 fitsfile
       real*8 bscale,bzero,gain,exptime
       character *2880 rhead

      open(2,file=fitsfile,status='old',access='direct',recl=nbyf)    
      gain=0.0d0
      headerr=0
      do i=1,maxheadrec
          read(2,rec=i) rhead

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

          ic=index(rhead,'GAIN    =')
          if(ic.ne.0) then
              read(rhead(ic+9:ic+29),'(f21.0)') gain
          endif

          ic=index(rhead,'EXPTIME =')
          if(ic.ne.0) then
              read(rhead(ic+9:ic+29),*) exptime
          endif

          ic=index(rhead,'END            ')
          if(ic.ne.0) then 
              goto 95
          endif
      enddo
95    close(2)
    end subroutine fits_header_main
    
      subroutine detect_gauss(fitsfile,bkgd_threshold,tele_label,sumi,starxx,staryy,snr,star_id,star_pix,overflag,nstar,bkgd,bkgdsigma)
!       function:detect stars and output the stars center(by gauss)
!          input:fitsfile:fits file name
!                bkgd_threshold:fitsdata-bkgd_threshold*bkgdsigma
!         output:sumi:the stars' flux
!                starxx:the x-position of star center
!                staryy:the x-position of star center
!                snr:the stars' snr
!                star_id:the id of the star( already sorted by brightness)
!                star_pix:The number of stars contained in star
!                overflag:Whether the stars overflow
!                nstar:Number of detected stars
!                bkgd:the image bkgd
!                bkgdsigma:the image bkgd
!Note:最大目标数量=naxis1*naxis2/pi/6**2  含最大像素数=pi*15**2, minpix=3
      
      implicit none
      character*200 fitsfile  
      character*100 tele_label
      integer*4 i,j,naxis1,naxis2,npx,bitpix,s,seq0,seq1,k,z,t,iloop
      integer*4 maxobj,minpix,maxpix,nli,nar,nstar,pos_nstar,p
      real*8 bzero,bscale,gain,bkgd,bkgdsigma,bkgd_threshold
      parameter(s=9000000)
      real*8 mdat(s),mdat01(s),abox(3000,3000),abox5(3000,3000),lty(4),x(5,1),a(400,5),b(400,1)
	  real*8 sumx(50000),sumy(50000),maxflux,sumi_real(50000),starx0(50000),stary0(50000)
      real*8 starx(50000),stary(50000),sumi(50000),pi,exptime,ss,h,starxx(50000),staryy(50000)
      integer*4 star_id(50000),star_pix(50000),overflag(50000)
	  real*8 pos_x(50000),pos_y(50000),pos_i(50000),snr(50000),snr01(50000)  
      integer*4 idpix(s),numpix(s),objpos(5000,5000)
      integer year,month,day,hh,mm,numobj
 	  integer nused,IFLAG1,ne
	  real*8 sigpar(5),rmag(500),sig0,sx,sy,si,b_noise
      
     pi=4*datan(1.0d0)
      bkgd=0
      bkgdsigma=0
!读取fits头文件及数据信息，并确定最大目标数maxobj、最大星象含像素数maxpix及溢出maxflux          
!最大目标数：假设视场中全是半径为6的星象，如ex: 1024*1056/3.1415/6/6=9561，实际是没有这么多的
!最大星象含像素数则是，定义半径为15的星象所含像素数，一般没有这么大的星象，最大半径仅5左右
      call fits_header_main(fitsfile,bitpix,naxis1,naxis2,bscale,bzero,gain,exptime)
      if(dabs(gain).le.1e-9) gain=1.0    
      maxflux=2**bitpix-1
      maxobj=int(naxis1*naxis2/pi/6**2)        
      minpix=3
      maxpix=int(pi*15**2)
      call fits_data(fitsfile,mdat,exptime,npx) 
      call cal_b(mdat,npx,bkgd,bkgdsigma)   !the whole image 
      
!连通域标号前对数据进行处理
!each pixes-（background＋bkgd_threshold*bkgdsigma）！bkgd_threshold一般设5，因图像改正过，sigma较小
      do i=1,npx
        mdat01(i)=mdat(i)-(bkgd+bkgd_threshold*bkgdsigma)
        if(mdat01(i).le.0.0d0) mdat01(i)=0.0d0
      enddo 
      abox=0.0
      do i=1,npx
        call seq2mat(i,naxis1,naxis2,nli,nar)    
        abox(nli,nar)=mdat01(i)
      enddo
!set the image edge pixel data =0
      do i=1,naxis2
        abox(i,1)=0.0d0
        abox(i,naxis1)=0.0d0
      enddo
      do j=1,naxis1
        abox(1,j)=0.0d0
        abox(naxis2,j)=0.0d0
      enddo
!!!!!需要时，可输出	
!    write(*,'(a,3i5,i8)'),'maxobj/minpix/maxpix/npx:',maxobj,minpix,maxpix,npx
      
!八邻域连通检测，对每像素标号
!lty1=右上，lty2=正上，lty3=左上，lty4=左
!目标号：numobj；像素标号idpix(numobj)=numobj,目标含像素数numpix(numobj)
!从上至下，从左至右逐个像素检测，当某像素>0时，分别做如下判断：
!1)其4邻均<0则：新建目标numobj+1，该目标像素数numpix(numobj)+1，该像素标号idpix(seq)=numobj
!2）lty1>0则：1的标号给当前像素，目标像素数+1
!3）lty2>0则：2的标号给当前像素，目标像素数+1
!4）lty3>0则：3的标号给当前像素，目标像素数+1
!5）lty4>0则：4的标号给当前像素，目标像素数+1
!maxobj设定检测目标数最大=全像素/孔径面积，若超过，结束标号并输出提示
!maxpix目标含像素数最多=2倍孔径圆像素,若超过，输出提示
!八连通域标号一次即可，不需要重复标号，不会出现重复编号
!编号原则：先扫描上一行3像素，有则设置同，再看左边同行，有则设置同，共计4个像素
      numobj=0
      numpix=0
      idpix=0
      objpos=0
      do i=2,naxis2-1
        do j=2,naxis1-1
          lty(1)=abox(i-1,j+1)
          lty(2)=abox(i-1,j)
          lty(3)=abox(i-1,j-1)
          lty(4)=abox(i,j-1)
          if(abox(i,j).gt.1d-9) then
            call mat2seq(i,j,naxis1,naxis2,seq0)
!星象只有一个像素，其余均0
            if(dabs(lty(1)+lty(2)+lty(3)+lty(4)).le.1d-9) then
              numobj=numobj+1
              idpix(seq0)=numobj !像素标号
              numpix(numobj)=numpix(numobj)+1  !目标累计像素
              objpos(idpix(seq0),numpix(numobj))=seq0
              if(numobj.gt.maxobj) then
                write(*,*)'Detect stars more than maxobj:',numobj,maxobj
                write(*,*)'Warning:Image quality problem!'
                goto 953
              endif
              if(numpix(numobj).gt.maxpix) then
                write(*,*)'Pixels of star more than maxpix:',numpix(numobj),maxpix
                write(*,*)'Warning:please check the radius value (maybe too small)!'
                goto 952
              endif                  
! 右上
            elseif(lty(1).gt.1d-9) then
              call mat2seq(i-1,j+1,naxis1,naxis2,seq1)            
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0
              if(numpix(idpix(seq0)).gt.maxpix) then
                write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                goto 952
              endif    
! 正上
            elseif(lty(2).gt.1d-9) then
              call mat2seq(i-1,j,naxis1,naxis2,seq1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0
              if(numpix(idpix(seq0)).gt.maxpix) then
                write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                goto 952
              endif     
! 左上         
            elseif(lty(3).gt.1d-9) then
              call mat2seq(i-1,j-1,naxis1,naxis2,seq1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0
              if(numpix(idpix(seq0)).gt.maxpix) then
                write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                goto 952
              endif     
! 左边      
            elseif(lty(4).gt.1d-9) then
              call mat2seq(i,j-1,naxis1,naxis2,seq1)
              idpix(seq0)=idpix(seq1)
              numpix(idpix(seq0))=numpix(idpix(seq0))+1
              objpos(idpix(seq0),numpix(idpix(seq0)))=seq0
              if(numpix(idpix(seq0)).gt.maxpix) then
                write(*,*)'Pixels of star more than maxpix:',numpix(idpix(seq0)),maxpix
                write(*,*)'Warning:please check the radius1 value (maybe too small)!'
                goto 952
              endif
            endif
          endif
952     enddo  !952 'this image includes super star(>pi*r^2)'
      enddo
! ========================结束连通域标号
953 continue   
!! ===================XZJ
!!compute the center of the object
! starx(k):x-value
! stary(k):y-value
! stari(k):flux-value（mdat01---has subtracted (bkgd+bkgd_threshold*bkgdsigma),not final value）！！
!注意，此处使用像素灰度值为mdat01(i)=mdat(i)-(bkgd+bkgd_threshold*bkgdsigma)  
      k=1
      sumx=0.0
      sumy=0.0 
      sumi=0.0
      starx=0.0
      stary=0.0       
      do i=1,numobj
        if(numpix(i).ge.minpix.and.numpix(i).le.maxpix) then
          do j=1,numpix(i)
            call seq2mat(objpos(i,j),naxis1,naxis2,nli,nar)  
            if(mdat01(objpos(i,j)).gt.maxflux) overflag(k)=1
            sumx(k)=sumx(k)+nli*mdat01(objpos(i,j))**2
            sumy(k)=sumy(k)+nar*mdat01(objpos(i,j))**2
            sumi(k)=sumi(k)+mdat01(objpos(i,j))**2 
            sumi_real(k)=sumi_real(k)+mdat(objpos(i,j))!用于输出亮度
            !仅用星象像素高斯
             ! a(j,1)=nli**2
             ! a(j,2)=nar**2
             ! a(j,3)=nli
             ! a(j,4)=nar
             ! a(j,5)=1.0
             !call mat2seq(nli,nar,naxis1,naxis2,seq0)
             !if(mdat(seq0).le.0) mdat(seq0)=1.0
             !b(j,1)=log(mdat(seq0))
          enddo
!maxim software:snr=sumi/bkgdsima/sqrt(pi*radius1**2)
!yuyong:tempsnrflux=sumvalue/dsqrt(sumvalue+numpix1*(bkgdsigma**2))
!tang:snr=mdat(i)-bkgd/bkgdsigma
          !  snr01(k)=sumi(k)/bkgdsigma/sqrt(numpix(i)) 
          !snr(k)=sumi(k)/sqrt(sumi(k)+numpix(i)*(bkgdsigma**2))
          snr(k)=sumi_real(k)/sqrt(sumi_real(k)+numpix(i)*(bkgdsigma**2)) !yuyong            
          starx(k)=sumx(k)/sumi(k)!记录修正矩结果
          stary(k)=sumy(k)/sumi(k)
          star_id(k)=i
          star_pix(k)=numpix(i)
      !=========修正矩中心为初值，6为半径，画圆圈求高斯
          t=0
100       if(starx(k).gt.6 .and.stary(k).gt.6 .and.starx(k).lt.(naxis1-6) .and.stary(k).lt.(naxis2-6)) then
          do p=1,11
             nli=int(starx(k))-6+p
             do z=1,11
                nar=int(stary(k))-6+z
        !  !guass parameters  
                t=t+1
                a(t,1)=nli**2
                a(t,2)=nar**2
                a(t,3)=nli
	            a(t,4)=nar
                a(t,5)=1.0
                !call mat2seq(nli,nar,naxis1,naxis2,seq0)
                !if(mdat01(seq0).le.0) mdat01(seq0)=1.0
                !b(t,1)=log(mdat01(seq0)) !使用减背景前
                if(abox(nli,nar).le.0) abox(nli,nar)=1.0
                b(t,1)=log(abox(nli,nar))!使用减背景后
                !print*,a(t,1:5),b(t,1)
                
               !t sx=sx+nli*abox(nli,nar)!**2
                !t sy=sy+nar*abox(nli,nar)!**2
                !t si=si+abox(nli,nar)!**2 
            enddo
          enddo
          !t starx(k)=sx/si
          !t stary(k)=sy/si
!实验，如果以xzj结果为中心画圈进行高斯定位，精度不稳定，0.07-0.09，zhj0.02左右
!现在使用和修正矩同样的像素计算，另外对于亮度采用减背景之前的数据mdat0
          call least(a(1:t,:),b(1:t,:),x,t,5,t,sigpar,sig0,nused,IFLAG1)
          !============画圈求中心位置↑
          !call least(a(1:numpix(i),:),b(1:numpix(i),:),x,numpix(i),5,numpix(i),sigpar,sig0,nused,IFLAG1)
          !LEAST(A,Y,X,N1,K,NE,ERROR,SITA2,nrefused,IFLAG1)
            starxx(k)=-1*x(3,1)/(2*x(1,1))
            staryy(k)=-1*x(4,1)/(2*x(2,1))
            !前后计算中心＜0.001迭代
           ! if(abs(starx(k)-starxx(k)).gt.0.001 .or.abs(stary(k)-staryy(k)).gt.0.001)then
           ! starx(k)=starxx(k)
           ! stary(k)=staryy(k)
           ! iloop=iloop+1
           ! goto 100
           ! endif
           ! print*,'iloop',iloop
            write(*,'(a,i7)')'numpix(i)',numpix(i)
            write(*,'(a,2f10.3)')'xzj:x-y',starx(k),stary(k)
            write(*,'(a,2f10.3)')'guass:x-y',starxx(k),staryy(k)
            write(*,'(a,2f10.3)')'xzj-guass:x-y',starx(k)-starxx(k),stary(k)-staryy(k)
            write(*,'(a,f7.3,i5)')'sig--nused',sig0,nused
       endif
        k=k+1
       endif
      enddo 
      nstar=k-1
       call sorting_7terms(sumi,starxx,staryy,snr,star_id,star_pix,overflag,nstar)   
!note: guass
      !z=ax^2+by^2+cx+dy+f  求解矩阵X（abcdf）
      !A=（x^2,y^2,x,y,1） 星象所有像素
      !B=z  像素灰度值
      !sigma_x^2=-a
      !sigma_y^2=-b
      !x0=-c/2a
      !y0=-d/2b
    end subroutine detect_gauss    
         
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
       parameter(s=9000000)
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
          if(fitsdata(npx).lt.0) fitsdata(npx)=fitsdata(npx)+65536  
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
          if(fitsdata(npx).lt.0) fitsdata(npx)=fitsdata(npx)+65536  
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

     subroutine cal_b(mdat,npx,bkgd,bkgdsigma)
!       function:calculate the background and bkgdsigma of fits
!          input:mdat：fitsdata
!                npx:the size of the mdat
!         output:bkgd:the average of fitsdata
!                bkgdsigma:Background relief
!注意：背景值为扣除>2.6sigma后两个sigma差异不大才为背景与sigma值
!      这样就避免了图像中星象的影响，仅为背景值和背景起伏
        implicit real*8(a-h,o-z)
        integer*4 npx
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



      subroutine sorting_7terms(x01,x02,x03,x04,x05,x06,x07,n)
!       function:according to he x01,reorder the sequencex01,x02,x03,x04,x05,x06,x07
!          input:x01,x02,x03,x04,x05,x06,x07:old sequence  
!                N:the size of sequence
!         output:x01,x02,x03,x04,x05,x06,x07:new sequence
      implicit real*8(a-h,o-z)
      real*8 x01(n),x02(n),x03(n),x04(n),tempx
      integer*4 x05(n),x06(n),x07(n),tempi

      do i=1,n-1
        k=i
        do j=i+1,n
          if(x01(j).ge.x01(k)) then
            k=j
          endif
        enddo
        tempx=x01(i)
        x01(i)=x01(k)
        x01(k)=tempx

        tempx=x02(i)
        x02(i)=x02(k)
        x02(k)=tempx

        tempx=x03(i)
        x03(i)=x03(k)
        x03(k)=tempx

        tempx=x04(i)
        x04(i)=x04(k)
        x04(k)=tempx

        tempi=x05(i)
        x05(i)=x05(k)
        x05(k)=tempi
    
        tempi=x06(i)
        x06(i)=x06(k)
        x06(k)=tempi   
            
        tempi=x07(i)
        x07(i)=x07(k)
        x07(k)=tempi 
      enddo
      end subroutine sorting_7terms

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
    
	SUBROUTINE LEAST(A,Y,X,N1,K,NE,ERROR,SITA2,nrefused,IFLAG1)
!    function:calculate the matrix X by least square
!       input:A:观测资料矩阵
!           Y:等号右侧矩阵
!           X:待解参数
!           N1:观测资料数量（方程数量）
!           K:待解参数数量
!           NE: 观测资料数量（方程数量）   
!    output:X:求解底片常数数值
!           ERROR:各个参数解算误差
!           SITA2:方程组结算误差（sqrt(sum(res**2)/nep-k)）??除号下是否应该直接是nep-1
!           nrefused：求解最终参数使用的观测数据数量
!           rmag：定义了，实际未用，应该是想要考虑亮度归算残差的
!           p：使用1与未使用0数据显示矩阵N1
!           vksi：ksi归算残差矩阵N1
!           vyit:yit归算残差矩阵N1
!           IFLAG1：如果迭代次数超过30次，标记为1，认为虽然星够，但是迭代不满足收敛条件
	 implicit real*8(a-h,o-z)
 	 REAL*8 A(N1,K),X(K,1),Y(N1,1),AT(K,NE),ATA(K,K),ATAAT(K,NE)
	 REAL*8 V(NE),V2(NE),SITA2,ERROR(K),P(NE),rmag(ne/2),vksi(ne/2),vyit(ne/2)
	 INTEGER IFLAG1
!a(400,5),b(400,1),x(5,1)

      parameter(SFA=2.6,SFB=0.01)
 
      IFLAG1=0
      pi=4*datan(1.0d0)
	  q=pi/180.0d0
      SITA2=0.0D0
      SITA2P=0.0D0
	  P=1.0
	  AT=0.0
	  NBIG=0
	  SITA20=0.0D0
!write(*,'(a,5f11.2)')'inleast a=',a(1:n1,1:5)
!pause
	  ILOOP=0
666	  NEP=NE-NBIG
	  SITA2P=SITA2
	  ILOOP=ILOOP+1
	  SITA2=0.0
	  DO I=1,K
 		DO J=1,NE
			AT(I,J)=A(J,I)
	    ENDDO
      ENDDO
      
	  DO I=1,NE
		DO J=1,K
			AT(J,I)=AT(J,I)*P(I)
		ENDDO
      ENDDO
!ATAX=ATY(最小二乘解超定方程组)
  	  CALL MUL(AT,A,ATA,K,NE,NE,K)
	  CALL MATINV(K,K,ATA)
      CALL MUL(ATA,AT,ATAAT,K,K,K,NE)
      CALL MUL(ATAAT,Y,X,K,NE,NE,1)
   !   print*,'x',x
    !xx=-1*x(3,1)/(2*x(1,1))!解中心位置
    !yy=-1*x(4,1)/(2*x(2,1))
    !print*,'xx-yy',xx,yy
    !pause     
!此处x即待解参数，K个
      v=0.0
 	  DO 10 I=1,NE
		DO 11 J=1,K
			V(I)=V(I)+A(I,J)*X(J,1)
11		    CONTINUE
		    V(I)=V(I)-Y(I,1)
		    V2(I)=V(I)**2
		    SITA2=SITA2+V2(I)*P(I)
10    CONTINUE
!只要剩余星象数量不少于待解参数，就计算其std，继续迭代
	        IF(NEP.NE.K) THEN 
               ! SITA2=DSQRT(SITA2/(NEP-1))!zz
		       SITA2=DSQRT(SITA2/(NEP-K))
	        ELSE
		       SITA2=0.0
	        ENDIF
            IF(DABS(SITA2-SITA20).GE.SFB*SITA20.AND.ILOOP.LE.30) THEN
		       SITA20=SITA2
		       NBIG=0
		       P=1.0
		       DO I=2,NE,2
		         IF(DABS(V(I)).GE.SFA*SITA2) THEN !若残差过大，则删除此星
				   P(I)=0.0
				   NBIG=NBIG+1
		         ENDIF
		       ENDDO
		       GOTO 666
            ELSEIF(ILOOP.GT.30) THEN
	           IFLAG1=1
            ENDIF
!            print*,'iloop=',iloop
!	        do i=2,ne,2
!		      vksi(i/2)=v(i-1)/q*3600.0
!		      vyit(i/2)=v(i)/q*3600.0
!	        enddo   
	        nrefused=ne-nbig
            DO 30 I=1,K
		       ERROR(I)=SITA2*SQRT(ATA(I,I))
30             CONTINUE
     END SUBROUTINE LEAST


	SUBROUTINE MUL(A1,A2,A12,K1,K2,K3,K4)
!    function:Two matrix multiplication
!    input:A1:matrix 1
!          A2:matrix 2        
!          K1/K2:A(K1,K2)
!          K3/K4:A(K3,K4)
!    output:A12:A12=A1*A2,A12(K1,K4)
    
	 implicit real*8(a-h,o-z)
      REAL*8 A1(K1,K2),A2(K3,K4),A12(K1,K4)
	  DO 30 I=1,K1
        DO 30 J=1,K4
           A12(I,J)=0.0
 30        CONTINUE
           DO 10 I=1,K1
		      DO 10 J=1,K4
			     L=1
 20			     A12(I,J)=A12(I,J)+A1(I,L)*A2(L,J)
                 L=L+1
			     IF(L.LE.K2) GOTO 20
 10	             CONTINUE
	 END SUBROUTINE MUL

	 SUBROUTINE MATINV (N,NUP,A)
!    function:Calculate the inverse matrix
!    input:N,NUP,A
!    output:A:new matrix
     
        IMPLICIT DOUBLE PRECISION (A-H,O-Z)
        DIMENSION A(N,N),B(1000),X(1000),EX(1000),IK(1000),JK(1000)
  10    DET=1.0D0
  11    DO 100 K=1,N
        AMAX=0.0D0
  21    DO 30 I=K,N
        DO 30 J=K,N
  23    IF (DABS(AMAX)-DABS(A(I,J))) 24,24,30
  24    AMAX=A(I,J)
        IK(K)=I
        JK(K)=J
  30    CONTINUE
  31    IF (AMAX) 41,32,41
  32    DET=0.0D0
        GOTO 140
  41    I=IK(K)
        IF (I-K) 21,51,43
  43    DO 50 J=1,N
        SAVE=A(K,J)
        A(K,J)=A(I,J)
  50    A(I,J)=-SAVE
  51    J=JK(K)
        IF (J-K) 21,61,53
  53    DO 60 I=1,N
        SAVE=A(I,K)
        A(I,K)=A(I,J)
  60    A(I,J)=-SAVE
  61    DO 70 I=1,N
        IF (I-K) 63,70,63
  63    A(I,K)=-A(I,K)/AMAX
  70    CONTINUE
  71    DO 80 I=1,N
        DO 80 J=1,N
        IF (I-K) 74,80,74
  74    IF (J-K) 75,80,75
  75    A(I,J)=A(I,J)+A(I,K)*A(K,J)
  80    CONTINUE
  81    DO 90 J=1,N
        IF (J-K) 83,90,83
  83    A(K,J)=A(K,J)/AMAX
  90    CONTINUE
        A(K,K)=1.0D0/AMAX
 100    DET=DET*AMAX
 101    DO 130 L=1,N
        K=N-L+1
        J=IK(K)
        IF (J-K) 111,111,105
 105    DO 110 I=1,N
        SAVE=A(I,K)
        A(I,K)=-A(I,J)
 110    A(I,J)=SAVE
 111    I=JK(K)
        IF (I-K) 130,130,113
 113    DO 120 J=1,N
        SAVE=A(K,J)
        A(K,J)=-A(I,J)
 120    A(I,J)=SAVE
 130    CONTINUE
 200	FORMAT (1X,'A(I,J)=',3F10.5,' B(I)=',F10.5)
        DO 138 J=1,N
        X(J)=0.D0
        DO 138 I=1,N
 138    X(J)=X(J)+A(I,J)*B(I)
 140	RETURN
    END SUBROUTINE MATINV
     
      
      subroutine least_square(a,b,x,m,n)
!fuction:Solving parameter sequence by least squares:AX=B-->ATAX=ATB
!m 待解参数个数列，n数据数量
!     use mkl
      integer m,n,i,L
      real*8 a(m,n),b(n,1),x(m,1)
      real*8 c(n,m),d(m,m),e(1,m)      
      !real*8 f(3,3),g(1,3),h(3,3)
      !data f/1,1,1,2,2,2,3,3,3/
      !data g/2,2,2/
      
      if (m<n) then
          c=transpose(a)
          d=matmul(a,c)
          e=matmul(c,b)
          call AGAUS(d,e,m,x)  
      else if(m==n) then
          call AGAUS(a,b,m,x)
      else
              write(*,'(a,i5,i5)') 'In least_square, m<n, No roots! m,n:',m,n
      endif
    end subroutine least_square

!求解线性方程组
    SUBROUTINE AGAUS(A,B,N,X) 
	DIMENSION A(N,N),X(N),B(N),JS(N) 
	DOUBLE PRECISION A,B,X,T 
	L=1 
	DO 50 K=1,N-1 
	  D=0.0 
	  DO 210 I=K,N 
	  DO 210 J=K,N 
	    IF (ABS(A(I,J)).GT.D) THEN 
	      D=ABS(A(I,J)) 
	      JS(K)=J 
	      IS=I 
	    END IF 
210   CONTINUE 
	  IF (D+1.0.EQ.1.0) THEN 
	    L=0 
	  ELSE 
	    IF (JS(K).NE.K) THEN 
	      DO 220 I=1,N 
	        T=A(I,K) 
	        A(I,K)=A(I,JS(K)) 
	        A(I,JS(K))=T 
220	      CONTINUE 
	    END IF 
	    IF (IS.NE.K) THEN 
	      DO 230 J=K,N 
	        T=A(K,J) 
	        A(K,J)=A(IS,J) 
	        A(IS,J)=T 
230	      CONTINUE 
	      T=B(K) 
	      B(K)=B(IS) 
	      B(IS)=T 
	    END IF 
	  END IF 
	  IF (L.EQ.0) THEN 
	   ! WRITE(*,100) 
	    RETURN 
	  END IF 
	  DO 10 J=K+1,N 
	    A(K,J)=A(K,J)/A(K,K) 
10	  CONTINUE 
	  B(K)=B(K)/A(K,K) 
	  DO 30 I=K+1,N 
	    DO 20 J=K+1,N 
	      A(I,J)=A(I,J)-A(I,K)*A(K,J) 
20	    CONTINUE 
	    B(I)=B(I)-A(I,K)*B(K) 
30	  CONTINUE 
50  CONTINUE 
	IF (ABS(A(N,N))+1.0.EQ.1.0) THEN 
	  L=0 
      !WRITE(*,100)
	  !write(*,*) 
	  RETURN 
	END IF 
	X(N)=B(N)/A(N,N) 
	DO 70 I=N-1,1,-1 
	  T=0.0 
	  DO 60 J=I+1,N 
	    T=T+A(I,J)*X(J) 
60	  CONTINUE 
	  X(I)=B(I)-T 
70	CONTINUE 
100 FORMAT(1X,' guass FAIL ') 
	JS(N)=N 
	DO 150 K=N,1,-1 
	  IF (JS(K).NE.K) THEN 
	    T=X(K) 
	    X(K)=X(JS(K)) 
	    X(JS(K))=T 
	  END IF 
150	CONTINUE 
	RETURN 
    END     
    