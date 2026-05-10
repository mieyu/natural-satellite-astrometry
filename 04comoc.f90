! **********************************CCD Image preprocessing*************************************
!program name: comoc.f90
! fuchtion：1）对前面计算出观测目标的O-C数据进行统计，剔除野值，统计最终数据的均值和标准偏差
!           2) 剔除模式1：使用（data-mean）绝对值大于几倍标准偏差的删除原则，设置std_limit，一般2.6倍，推荐
!           3）剔除模式2：使用（data-mean）绝对值大于某设定数值的删除原则，设置mean_limit,一般控制标准偏差不大于0.03
!           4) 可选择是否删除前面所有过程文件：当确定数据无误时可设置del_flag=1，如果在调试阶段，建议设0
!    input：0）(注意修改specified_output=注意设置日期，避免混乱)
!           1) 配置文件信息（adias.cfg）
!               1.1）fits图像路径：1fitspath=D:\CCD_DATA\obs\fitspath.in
!               1.2）指定观测结果输出文件：4specified-output=D:\00Adias\obs\20060825.out
!               1.3）使用标准偏差模式：4std_limit=2.6
!               1.4）使用限制残差模式：4mean_limit=0.03 
!               1.5）设置是否删除过程文件：4del_flag=0
!           2）由前面计算得到的数据文件：object.out 
!   output：1）剔除野值后数据(图像文件夹)：final_object.out/final_object_oc.out  /...fits folder
!           2）放入指定文件夹的数据：如20060825.out/20060825_oc.out/20060825_obsdata.out
! by zhy 2019.08.25
! V3.0  Chinese comment by zhy 2020.01.31
    
    
      program comoc
      implicit none
      integer*4 ic,ic1,m,i,j,n_obj,n_new,iloop,del_flag,n_obj0,obj,obj_total
      character*1 obj_label
      parameter(m=10000)
      character*300 tempcha(m),new_tempcha(m),templine
      character*300 fitspath,objoutfile,newoutfile,o_cfile,newoutfile0
      character*300 newoutfile1,o_cfile1,obsdatafile,alloutfile,month_outfile
      real*8 res_ra(m),res_de(m),new_ra(m),new_de(m),ocra(m),ocde(m)
      real*8 mean_ra,mean_de,std_ra,std_de,oc_limit,mean_limit
      real*8 mean_ra0,mean_de0,std_ra0,std_de0,eps
       integer*4 n_day

!01--读配置文件          
     open(11,file='adias.cfg')
    !      open(11,file='D:\00adias\exe\200809adias.cfg') !!!!!!!!!!!!!!!!!!!!!!!调试用
      do i=1,m
        read(11,'(a100)',end=1000) templine
        
       ! ic=index(templine,'1fitspath=')
       ! if(ic.gt.0) then
       !   ic1=index(templine,'=')
       !   read(templine(ic1+1:ic1+100),*) fitsfilepath
       ! endif 
        ic=index(templine,'3obj_total=')
        if(ic.gt.0) then
          ic1=index(templine,'=')
          read(templine(ic1+1:ic1+30),*) obj_total !待处理目标数
        endif  
        
        ic=index(templine,'4specified-output=')
        if(ic.gt.0) then
          ic1=index(templine,'=')
          read(templine(ic1+1:ic1+100),*) newoutfile0
        endif 

        ic=index(templine,'4eps=')
        if(ic.gt.0) then
          ic1=index(templine,'=')
          read(templine(ic1+1:ic1+30),*) eps
        endif
        
        ic=index(templine,'4std_limit=')
        if(ic.gt.0) then
          ic1=index(templine,'=')
          read(templine(ic1+1:ic1+30),*) oc_limit
        endif

        ic=index(templine,'4mean_limit=')
        if(ic.gt.0) then
          ic1=index(templine,'=')
          read(templine(ic1+1:ic1+30),*) mean_limit
        endif
        
        ic=index(templine,'4del_flag=')
        if(ic.gt.0) then
          ic1=index(templine,'=')
          read(templine(ic1+1:ic1+30),*) del_flag
        endif

      enddo
1000  close(11)
!      eps=0.2
!      oc_limit=100.0
 
!02--如果配置文件删除标识设置1，则删除过程文件
!该标志慎用，如果确定中间结果没有问题可以删除
   !   open(12,file='delfile.bat',status='replace')
   !   write(12,'(2a)') 'cd /d ',trim(newoutfile0)
!	  write(12,'(a)') 'del *.dat'
!	  close(12)       
 !     call system('delfile.bat') 
  !    write(*,*)  '   过程文件已删除!!（*.dat）'
      obj=0
9999 obj=obj+1 !用于标记目标数     
      write(obj_label,'(i1)')obj
      o_cfile=trim(newoutfile0)//'\'//'00oc_'//trim(obj_label)//'.out'
      open(3,file=o_cfile,status='unknown',access='append')
      open(1,file='fitspath.in',status='old')   
  !        open(1,file='D:\00adias\exe\200809fitspath.in',status='old') !!!!!!!!!!!!!!!!!!!!!!!调试用
       n_day=0
       read(1,'(a100)',end=777) fitspath
       ic=index(fitspath,'WZYT')!========================================================================================不同望远镜修改
       ic1=len(trim(fitspath))
       !用以输出每月数据
        month_outfile=trim(newoutfile0)//trim(fitspath(ic+4:ic1-14))//trim(obj_label)//'.dat'
        open(18,file=month_outfile,status='unknown',access='append')
        close(1)
       open(1,file='fitspath.in',status='old') 
 !       open(1,file='D:\00adias\exe\200809fitspath.in',status='old') !!!!!!!!!!!!!!!!!!!!!!!调试用
77     read(1,'(a100)',end=777) fitspath
       fitspath=trim(fitspath)
       n_day=n_day+1  !用以记录共处理几天数据
       write(*,*)
    write(*,'(i3,a,a,a)')  n_day,'-','本日fits文件：',trim(fitspath)
    
!   按照配置文件内容逐日处理
    newoutfile=newoutfile0
      
!02--如果配置文件删除标识设置1，则删除过程文件
!该标志慎用，如果确定中间结果没有问题可以删除
    if(del_flag .eq.1)then
      open(12,file='delfile.bat',status='replace')
      write(12,'(2a)') 'cd /d ',trim(fitspath)
	  write(12,'(a)') 'del *_n.fit'
      write(12,'(a)') 'del *.reg'
	  close(12)       
      call system('delfile.bat') 
      write(*,*)  '   过程文件已删除!!（*_n.fit,*.reg）'
    endif
    
!03--编辑输出文件名      
    objoutfile=trim(fitspath)//'\object_'//trim(obj_label)//'.out'!match得到结果
    newoutfile1=trim(fitspath)//'\final_object_'//trim(obj_label)//'.out'!删除大于剔除标准的数据
    o_cfile1=trim(fitspath)//'\final_oc_'//trim(obj_label)//'.out'    !统计数据归算残差
!同时输出到指定同一个文件夹，时间.out/_oc.out/obsdata,方便统一整理
    newoutfile=trim(newoutfile)//fitspath((len(trim(fitspath))-13):(len(trim(fitspath))-5))//trim(obj_label)//'.out'
    ic=index(newoutfile,'.')
    ic1=len(trim(newoutfile))
    !o_cfile=trim(newoutfile(1:ic-1))//'_oc'//'.out'
    obsdatafile=trim(newoutfile(1:ic-1))//'_obsdata_'//trim(obj_label)//'.out'
    alloutfile=trim(newoutfile(1:ic-1))//'_all_'//trim(obj_label)//'.out'!为方便matlab调用，输出文件删去图像路径信息,文件存储到指定文件夹
!04--读数据文件计算平均值与标准偏差
!分为原始数据与剔除后数据，所有统计结果分别在2个文件和屏幕输出
    open(2,file=objoutfile)
    open(4,file=newoutfile,status='replace')
    open(14,file=alloutfile,status='replace')
    
    open(5,file=o_cfile1,status='replace')!output to this fits folder
    open(6,file=newoutfile1,status='replace')
    open(7,file=obsdatafile,status='replace')
    n_obj=0
    res_ra=0.0
    res_de=0.0
    ocra=0
    ocde=0
    do i=1,m
        read(2,'(a300)',end=111) tempcha(i)
        write(14,'(a147)')tempcha(i)
        read(tempcha(i),'(95x,2f10.4,55x)') res_ra(i),res_de(i)
        n_obj=n_obj+1
    enddo    
111 close(2)
    close(14)
!041--统计原始数据均值与标准偏差，并输出（根据选择限制残差大小或者剔除限）   
    mean_ra0=sum(res_ra)/n_obj
    mean_de0=sum(res_de)/n_obj
    do i=1,n_obj
        ocra(i)=(res_ra(i)-mean_ra0)**2
        ocde(i)=(res_de(i)-mean_de0)**2
    enddo
        std_ra0=sqrt(sum(ocra)/(n_obj-1))
        std_de0=sqrt(sum(ocde)/(n_obj-1))

    !write(3,*)          '=================res数据统计结果================='
    !write(3,'(a,i4)')   '  原始数据数量n_obj：',n_obj
    !write(3,'(a,2f9.4)')'  原始数据均值ra,de：',mean_ra0,mean_de0
    !write(3,'(a,2f9.4)')'  原始数据方差ra,de：',std_ra0,std_de0
    !if(oc_limit .gt.0.0)then
    !    write(3,'(a,f5.2,a)')'*********剔除野值标准(oc_limit)：',oc_limit,'  *********'
    !else
    !    write(3,'(a,f5.2,a)')'*********剔除野值标准(mean_limit)：',mean_limit,'  *********'
    !endif
        if(n_obj.lt.2)then       !20220718避免由于计算公式中分母为0导致格式错误
            mean_ra0=999.999
            mean_de0=999.999
            std_ra0=999.999
            std_de0=999.999
        end if 
    write(5,'(a)')      '=================res数据统计结果================='
    write(5,'(a,i4)')   '  原始数据数量n_obj：',n_obj
    write(5,'(a,2f12.4)')'  原始数据均值ra,de：',mean_ra0,mean_de0
    write(5,'(a,2f12.4)')'  原始数据方差ra,de：',std_ra0,std_de0
    if(oc_limit .gt.0.0)then
        write(5,'(a,f5.2,a)')'*********剔除野值标准(oc_limit)：',oc_limit,'  *********'
    else
        write(5,'(a,f5.2,a)')'*********剔除野值标准(mean_limit)：',mean_limit,'  *********'
    endif
    
    write(*,*)          '================04Comoc-Program execution summary==================' 
    write(*,*)          '=================res数据统计结果================='
    write(*,'(a,i4)')   '  原始数据数量n_obj：',n_obj
    write(*,'(a,2f12.4)')'  原始数据均值ra,de：',mean_ra0,mean_de0
    write(*,'(a,2f12.4)')'  原始数据方差ra,de：',std_ra0,std_de0
    if(oc_limit .gt.0.0)then
        write(*,'(a,f5.2,a)')'*********剔除野值标准(oc_limit)：',oc_limit,'  *********'
    else
        write(*,'(a,f5.2,a)')'*********剔除野值标准(mean_limit)：',mean_limit,'  *********'
    endif
     !汇总一个观测时段（原始数据月）   
 !    do i=1,n_obj
  !     write(18,'(a148)') tempcha(i)
   ! enddo 
    
    n_obj0=n_obj
    mean_ra=mean_ra0
    mean_de=mean_de0
    std_ra=std_ra0
    std_de=std_de0
!041--统计原始数据均值与标准偏差，并输出（根据选择限制残差大小或者剔除限）
    iloop=1
222 n_new=1
    new_tempcha='  '
    new_ra=0.0
    new_de=0.0
    ocra=0
    ocde=0
    do i=1,n_obj
      if(oc_limit.gt.0.0) then !if oc_limit was given value,use oc_limit.or use mean_limit
        if((abs(res_ra(i)-mean_ra).lt.oc_limit*std_ra).and.(abs(res_de(i)-mean_de).lt.oc_limit*std_de)&
            &.and. abs(res_ra(i)).lt.eps.and.abs(res_de(i)).lt.eps)then
            !&.and. abs(res_ra(i)).lt.0.15.and.abs(res_de(i)).lt.0.15)then
            new_tempcha(n_new)=tempcha(i)
            new_ra(n_new)=res_ra(i)
            new_de(n_new)=res_de(i)
            n_new=n_new+1
        endif
      else !use mean_limit
       if((abs(res_ra(i)-mean_ra).lt.mean_limit).and.(abs(res_de(i)-mean_de).lt.mean_limit))then
            new_tempcha(n_new)=tempcha(i)
            new_ra(n_new)=res_ra(i)
            new_de(n_new)=res_de(i)
            n_new=n_new+1
        endif
      endif
    enddo
  
    n_new=n_new-1
    mean_ra=sum(new_ra)/n_new
    mean_de=sum(new_de)/n_new
    do i=1,n_new
        ocra(i)=(new_ra(i)-mean_ra)**2
        ocde(i)=(new_de(i)-mean_de)**2
    enddo
    std_ra=sqrt(sum(ocra)/(n_new-1))
    std_de=sqrt(sum(ocde)/(n_new-1))
    if(n_obj .gt. n_new)then
        tempcha=new_tempcha
        res_ra=new_ra
        res_de=new_de
        n_obj=n_new
        iloop=iloop+1
        goto 222
    endif
    if(n_obj0<1)then
        mean_ra0=0
        mean_de0=0
        std_ra0=0
        std_de0=0
        n_new=0
        mean_ra=0
        mean_de=0
        std_ra=0
        std_de=0
    elseif(n_new<1)then
        n_new=0
        mean_ra=0
        mean_de=0
        std_ra=0
        std_de=0
    endif
    !write(3,'(a,i4)')   '  剔除野值后数据数量n_new：',n_new
    !write(3,'(a,2f9.4)')'  剔除野值后数据均值ra,de：',mean_ra,mean_de
    !write(3,'(a,2f9.4)')'  剔除野值后数据方差ra,de：',std_ra,std_de 
    !write(3,'(a,i2)')   '  剔除野值迭代次数：',iloop 
        if(n_obj.lt.2)then       !20220718避免由于计算公式中分母为0导致格式错误
            mean_ra=999.999
            mean_de=999.999
            std_ra=999.999
            std_de=999.999
        end if 
    write(5,'(a,i4)')   '  剔除野值后数据数量n_new：',n_new
    write(5,'(a,2f12.4)')'  剔除野值后数据均值ra,de：',mean_ra,mean_de
    write(5,'(a,2f12.4)')'  剔除野值后数据方差ra,de：',std_ra,std_de 
    write(5,'(a,i2)')   '  剔除野值迭代次数：',iloop 
    
    write(*,'(a,i4)')   '  剔除野值后数据数量n_new：',n_new
    write(*,'(a,2f12.4)')'  剔除野值后数据均值ra,de：',mean_ra,mean_de
    write(*,'(a,2f12.4)')'  剔除野值后数据方差ra,de：',std_ra,std_de 
    write(*,'(a,i2)')   '  剔除野值迭代次数：',iloop 
    write(*,'(a,a)')    '  残差文件输出:',o_cfile    
 !200608 原始数量  精度 剔除后数量 精度 写oc文件
    
    if(std_ra.lt.0.3.and.std_de.lt.0.3.and.n_new.gt.1)then  !输出标准偏差小于0.05的，大于此值，数据质量不好
!方便latex文件，加入间隔符号&
        write(3,'(a,a,i4,a,f9.3,a,f9.3,a,f9.3,a,f9.3,a,i4,a,f9.3,a,f9.3,a,f9.3,a,f9.3)') fitspath((len(trim(fitspath))-12):(len(trim(fitspath))-5)),&
            &' & ',n_obj0,' & ',mean_ra0,' & ',mean_de0,' & ',std_ra0,' & ',std_de0,' & ',n_new,' & ',mean_ra,' & ',mean_de,' & ',std_ra,' & ',std_de
 ! oc文件不输出间隔符号&
 !       write(3,'(a,i4,4f9.4,i4,4f9.4)') fitspath((len(trim(fitspath))-12):(len(trim(fitspath))-5)),&
 !           & n_obj0,mean_ra0,mean_de0,std_ra0,std_de0,n_new,mean_ra,mean_de,std_ra,std_de
        write(*,'(a,i4,4f9.4,i4,4f9.4)') fitspath((len(trim(fitspath))-12):(len(trim(fitspath))-5)),&
            & n_obj0,mean_ra0,mean_de0,std_ra0,std_de0,n_new,mean_ra,mean_de,std_ra,std_de

     do i=1,n_new
        write(4,'(a147)') new_tempcha(i)!为方便matlab调用，输出文件删去图像路径信息
        write(6,'(a300)') new_tempcha(i)
        write(7,'(a48)')  new_tempcha(i)!可提交IMCCE的数据格式
        write(18,'(a147)') new_tempcha(i)
     enddo   
    
    else
        print*,'删除该日期数据：============'
        write(*,'(a,i4,4f9.4,i4,4f9.4)') fitspath((len(trim(fitspath))-12):(len(trim(fitspath))-5)),&
            & n_obj0,mean_ra0,mean_de0,std_ra0,std_de0,n_new,mean_ra,mean_de,std_ra,std_de
        print*,'================'
    endif
!处理下一天数据
    goto 77 
777 close(1)
    if(obj.lt.obj_total)     goto 9999 !若小于总目标数，跳转，重新赋值参考星和历表文件路径
    write(*,'(a,i3)') '   本日匹配共归算天然卫星目标个数',obj
    write(*,'(a)')    '================================================================='      

    close(3)
    close(4)
    close(5)
    close(6)
    close(7)
    close(18)
    write(*,'(a,i3)') '数据统计归算结束，共处理数据天数：',n_day
    write(*,'(a)')    '================================================================='
    write(*,*)        '=====================ADIAS END======================' 

    call music
    end program comoc

!
	SUBROUTINE MUSIC
! 
    !   call BEEPQQ (340, 150)
    !   call BEEPQQ (380, 150)
    !   call BEEPQQ (420, 150)
    !   call BEEPQQ (440, 150)
    !   call BEEPQQ (500, 300)
    !   call BEEPQQ (340, 300)
    !   call BEEPQQ (340, 300)

   !   call BEEPQQ (560, 300)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (500, 150)
   !   call BEEPQQ (560, 150)
	  !call BEEPQQ (620, 150)
   !   call BEEPQQ (660, 300)
   !   call BEEPQQ (340, 300)
   !   call BEEPQQ (340, 300)

   !   call BEEPQQ (440, 300)
   !   call BEEPQQ (500, 150)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (420, 150)
	  !call BEEPQQ (380, 150)
   !   call BEEPQQ (420, 300)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (420, 150)
   !   call BEEPQQ (380, 150)
   !   call BEEPQQ (340, 150)
   !   call BEEPQQ (320, 300)
   !   call BEEPQQ (340, 150)
   !   call BEEPQQ (380, 150)
   !   call BEEPQQ (420, 150)
   !   call BEEPQQ (340, 150)
   !   call BEEPQQ (420, 300)
   !   call BEEPQQ (380, 300)
   !   call BEEPQQ (380, 300)

   !   call BEEPQQ (500, 300)
   !   call BEEPQQ (340, 150)
   !   call BEEPQQ (380, 150)
   !   call BEEPQQ (420, 150)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (500, 300)
   !   call BEEPQQ (340, 300)
   !   call BEEPQQ (340, 300)
   !
   !   call BEEPQQ (560, 300)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (500, 150)
   !   call BEEPQQ (560, 150)
	  !call BEEPQQ (620, 150)
   !   call BEEPQQ (660, 300)
   !   call BEEPQQ (340, 300)
   !   call BEEPQQ (340, 300)
   !
   !   call BEEPQQ (440, 300)
   !   call BEEPQQ (500, 150)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (420, 150)
	  !call BEEPQQ (380, 150)
   !   call BEEPQQ (420, 300)
   !   call BEEPQQ (440, 150)
   !   call BEEPQQ (420, 150)
   !   call BEEPQQ (380, 150)      
	  !call BEEPQQ (340, 150)
   !   
	  !call BEEPQQ (380, 300)
   !   call BEEPQQ (420, 150)
   !   call BEEPQQ (380, 150)
	  !call BEEPQQ (340, 150)
   !   call BEEPQQ (320, 150)
   !   call BEEPQQ (340, 500)
	  RETURN
!	STOP
	END

    